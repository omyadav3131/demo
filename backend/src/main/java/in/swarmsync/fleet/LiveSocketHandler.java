package in.swarmsync.fleet;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/** Pushes every new snapshot to all dashboards instantly (no polling). */
@Component
public class LiveSocketHandler extends TextWebSocketHandler {
    private final Set<WebSocketSession> sessions = ConcurrentHashMap.newKeySet();
    private final FleetStore store;

    public LiveSocketHandler(FleetStore store) { this.store = store; }

    @Override
    public void afterConnectionEstablished(WebSocketSession s) {
        sessions.add(s);
        if (store.getState() != null) send(s, store.getState());
        if (store.getReport() != null) send(s, "{\"report\":" + store.getReport() + "}");
    }

    @Override
    public void afterConnectionClosed(WebSocketSession s, CloseStatus status) { sessions.remove(s); }

    public void broadcast(String json) { for (WebSocketSession s : sessions) send(s, json); }

    private void send(WebSocketSession s, String json) {
        try {
            synchronized (s) { if (s.isOpen()) s.sendMessage(new TextMessage(json)); }
        } catch (IOException e) { sessions.remove(s); }
    }
}
