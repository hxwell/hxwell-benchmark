package benchapp;

import hx.well.http.Request;

@:access(hx.well.http.driver.crossbyte.CrossbyteDriverContext)
@:access(hx.well.http.driver.crossbyte.CrossbyteDriver)
class DriverStats {
    public static function read(request:Request):Dynamic {
        var context:hx.well.http.driver.crossbyte.CrossbyteDriverContext = cast request.context;
        var server = context.driver.server;
        return {refused:server.refusedConnections, connections:server.connectionCount,
                maxWaiting:crossbyte.net._internal.ServerSpread.MAX_WAITING};
    }
}
