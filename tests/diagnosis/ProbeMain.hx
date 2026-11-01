import crossbyte.core.CrossByte;
import crossbyte.core.HostApplication;
import crossbyte.events.Event;
import crossbyte.http.HTTPRequestHandler;
import crossbyte.http.HTTPResponseStream;
import crossbyte.http.HTTPServer;
import crossbyte.http.HTTPServerConfig;
import crossbyte.io.ByteArray;
import crossbyte.url.URLRequestHeader;
import crossbyte.utils.Logger;
import crossbyte.utils.LogLevel;
import haxe.io.Bytes;
import jvm.thread.VirtualThread;
import sys.thread.Lock;

class ProbeMain {
    static var server:HTTPServer;
    static var body = ByteArray.fromBytes(Bytes.ofString("Hello, World!\n"));
    static var mode = Sys.getEnv("DIAG_MODE") ?? "buffered";
    static var keep = [new URLRequestHeader("Connection", "keep-alive")];

    public static function main():Void {
        Logger.level = LogLevel.WARN;
        Logger.timestamps = true;
        Logger.sink = line -> { Sys.stderr().writeString(line + "\n"); Sys.stderr().flush(); };
        var waiting = Sys.getEnv("DIAG_WAITING");
        if(waiting != null) crossbyte.net._internal.ServerSpread.MAX_WAITING = Std.parseInt(waiting);
        haxe.EntryPoint.runInMainThread(() -> {});
        var host = new ProbeHost();
        host.advance(0);
        CrossByte.make(POLL, HEAP, runtime -> runtime.addEventListener(Event.INIT, _ -> {
            var config = new HTTPServerConfig("127.0.0.1", Std.parseInt(Sys.getEnv("BENCH_PORT")));
            config.maxConnections = 4000;
            config.runtimeCount = Std.parseInt(Sys.getEnv("DIAG_RUNTIMES") ?? "2");
            config.rateLimitKey = _ -> null;
            config.compression.enabled = false;
            config.keepAliveMaxRequests = 0;
            config.keepAliveTimeout = 30;
            config.http2Enabled = false;
            config.phpEnabled = false;
            config.rootDirectory = null;
            config.middleware = [(handler, next) -> handle(handler)];
            server = new HTTPServer(config);
        }));
    }

    static function handle(handler:HTTPRequestHandler):Void {
        if(handler.requestPath == "/health") {
            handler.respond(200, "application/json", haxe.Json.stringify({ready:true, refused:server.refusedConnections, connections:server.connectionCount, maxWaiting:crossbyte.net._internal.ServerSpread.MAX_WAITING}), keep);
            return;
        }
        switch(mode) {
            case "buffered": handler.respondBytes(200, "text/plain", body, keep);
            case "stream":
                var stream = handler.beginResponse(200, "text/plain", keep);
                stream.write(body);
                stream.end();
            case "posted-stream":
                var owner = CrossByte.current();
                VirtualThread.create(() -> {
                    var stream:HTTPResponseStream = null;
                    try {
                        handoff(owner, () -> stream = handler.beginResponse(200, "text/plain", keep));
                        handoff(owner, () -> stream.write(body));
                        handoff(owner, () -> stream.end());
                    } catch(error:Dynamic) {
                        Sys.stderr().writeString("CONTROL_ERROR " + Sys.time() + " " + Std.string(error) + "\n");
                    }
                }).start();
            default: throw "Unknown mode";
        }
    }

    static function handoff(owner:CrossByte, action:Void->Void):Void {
        var done = new Lock();
        var failure:Dynamic = null;
        if(!owner.post(() -> {
            try { action(); } catch(error:Dynamic) { failure = error; }
            done.release();
        }) || !done.wait(30)) throw "Control response handoff timed out";
        if(failure != null) throw failure;
    }
}

private class ProbeHost extends HostApplication {
    public function new() { super(); }
}
