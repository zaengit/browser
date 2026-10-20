// Browser: minimal on-device inspector integrated into Chromium Android.
// No WebView, root, TCP debug listener or third-party packages are used.
package org.chromium.chrome.browser.devtools;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Launch as the "Browser DevTools" second launcher icon while Chromium is running.
 *
 * CDP traffic connects directly to the Chromium app's Unix abstract socket.
 * Never expose the socket through an HTTP server/loopback TCP port.
 */
public final class InspectorActivity extends Activity {
    private static final String SOCKET_NAME = "browserfork_devtools_remote";
    private static final int MAX_FRAME = 8 * 1024 * 1024;
    private final ExecutorService executor = Executors.newCachedThreadPool();
    private final Handler main = new Handler(Looper.getMainLooper());

    private LinearLayout root;
    private TextView status;
    private TextView output;
    private ScrollView scroll;
    private EditText command;
    private CdpClient client;
    private String selectedPanel = "Console";
    private final StringBuilder consoleText = new StringBuilder();
    private final StringBuilder networkText = new StringBuilder();
    private String elementsText = "Select a tab and tap Refresh DOM.";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(18, 18, 18, 18);
        setContentView(root);

        LinearLayout tools = row();
        Button tabs = button("Select tab", () -> executor.execute(this::loadTabs));
        tools.addView(tabs);
        Button refresh = button("Refresh DOM", this::refreshDom);
        tools.addView(refresh);
        root.addView(tools);
        status = new TextView(this);
        status.setText("Connecting to Chromium...");
        status.setTextSize(13);
        root.addView(status);

        LinearLayout panels = row();
        for (String name : new String[]{"Elements", "Console", "Network"}) {
            panels.addView(button(name, () -> {
                selectedPanel = name;
                render();
            }));
        }
        root.addView(panels);

        scroll = new ScrollView(this);
        output = new TextView(this);
        output.setTextIsSelectable(true);
        output.setTextSize(12);
        output.setPadding(8, 8, 8, 8);
        scroll.addView(output);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout bottom = row();
        command = new EditText(this);
        command.setSingleLine(true);
        command.setHint("JavaScript expression...");
        command.setInputType(InputType.TYPE_CLASS_TEXT);
        bottom.addView(command, new LinearLayout.LayoutParams(0, -2, 1));
        bottom.addView(button("Run", this::evaluate));
        root.addView(bottom);
        render();
        executor.execute(this::loadTabs);
    }

    private LinearLayout row() {
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setOrientation(LinearLayout.HORIZONTAL);
        return row;
    }

    private Button button(String label, Runnable callback) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(11);
        button.setAllCaps(false);
        button.setOnClickListener(v -> callback.run());
        return button;
    }

    private void loadTabs() {
        try {
            JSONArray all = new JSONArray(requestTargets());
            List<JSONObject> pages = new ArrayList<>();
            List<String> labels = new ArrayList<>();
            for (int i = 0; i < all.length(); ++i) {
                JSONObject target = all.getJSONObject(i);
                if (!"page".equals(target.optString("type"))) continue;
                if (!target.has("webSocketDebuggerUrl")) continue;
                pages.add(target);
                String title = target.optString("title", "(untitled)");
                labels.add(title + "\n" + target.optString("url", ""));
            }
            main.post(() -> {
                if (isFinishing() || isDestroyed()) return;
                if (pages.isEmpty()) {
                    status.setText("No Chromium page targets. Open a page first and retry.");
                    return;
                }
                new AlertDialog.Builder(this)
                        .setTitle("Inspect a Chromium tab")
                        .setItems(labels.toArray(new String[0]), (dialog, which) -> {
                            JSONObject target = pages.get(which);
                            status.setText("Opening: " + target.optString("title"));
                            executor.execute(() -> connectTarget(target));
                        })
                        .setNegativeButton("Cancel", null).show();
            });
        } catch (Exception error) {
            setStatus("Cannot list tabs: " + error.getMessage()
                    + ". Start Chromium and retry.");
        }
    }

    private String requestTargets() throws IOException {
        try (LocalSocket socket = openSocket()) {
            socket.setSoTimeout(5000);
            OutputStream out = socket.getOutputStream();
            out.write(("GET /json/list HTTP/1.1\r\nHost: localhost\r\n"
                    + "Connection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
            out.flush();
            InputStream in = socket.getInputStream();
            String headers = readHeaders(in);
            if (!headers.startsWith("HTTP/1.1 200") && !headers.startsWith("HTTP/1.0 200")) {
                throw new IOException("Target listing HTTP error: " + headers.split("\r\n")[0]);
            }
            // Debug discovery response is small; bounded read until connection closes.
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int count;
            while ((count = in.read(buffer)) != -1) {
                if (body.size() + count > 1024 * 1024) throw new IOException("Target list too large");
                body.write(buffer, 0, count);
            }
            return body.toString("UTF-8");
        }
    }

    private void connectTarget(JSONObject target) {
        try {
            String path = target.getString("webSocketDebuggerUrl")
                    .replaceFirst("^wss?://[^/]+", "");
            if (!path.matches("/devtools/page/[A-Za-z0-9_-]+")) {
                throw new IOException("Unsafe target path: " + path);
            }
            CdpClient old = client;
            if (old != null) old.close();
            CdpClient next = new CdpClient(path);
            next.connect();
            client = next;
            synchronized (consoleText) { consoleText.setLength(0); }
            synchronized (networkText) { networkText.setLength(0); }
            elementsText = "Refresh DOM to see the element tree.";
            main.post(() -> { status.setText("Inspecting: " + target.optString("title")); render(); });
            executor.execute(() -> next.readLoop());
            next.send("Runtime.enable", new JSONObject());
            next.send("DOM.enable", new JSONObject());
            next.send("Network.enable", new JSONObject());
            refreshDom();
        } catch (Exception error) {
            setStatus("CDP connection failed: " + error.getMessage());
        }
    }

    private void refreshDom() {
        CdpClient connected = client;
        if (connected == null) { setStatus("Choose a tab first."); return; }
        try {
            connected.send("DOM.getDocument", new JSONObject().put("depth", 4));
        } catch (Exception e) { setStatus("DOM command failed: " + e.getMessage()); }
    }

    private void evaluate() {
        CdpClient connected = client;
        if (connected == null) { setStatus("Choose a tab first."); return; }
        String expression = command.getText().toString();
        if (expression.isEmpty()) return;
        try {
            connected.send("Runtime.evaluate", new JSONObject()
                    .put("expression", expression)
                    .put("returnByValue", true)
                    .put("awaitPromise", true));
            appendConsole("> " + expression);
            command.setText("");
        } catch (Exception e) { setStatus("Console command failed: " + e.getMessage()); }
    }

    private void handleMessage(String data) {
        try {
            JSONObject msg = new JSONObject(data);
            String method = msg.optString("method");
            JSONObject params = msg.optJSONObject("params");
            if ("Runtime.consoleAPICalled".equals(method) && params != null) {
                JSONArray args = params.optJSONArray("args");
                StringBuilder line = new StringBuilder(params.optString("type")).append(": ");
                if (args != null) for (int i = 0; i < args.length(); i++) {
                    JSONObject arg = args.optJSONObject(i);
                    if (arg != null) line.append(arg.optString("value",
                            arg.optString("description", "[object]"))).append(" ");
                }
                appendConsole(line.toString());
            } else if ("Runtime.exceptionThrown".equals(method) && params != null) {
                appendConsole("ERROR: " + params.toString());
            } else if ("Network.requestWillBeSent".equals(method) && params != null) {
                JSONObject req = params.optJSONObject("request");
                if (req != null) appendNetwork("→ " + req.optString("method")
                        + " " + req.optString("url"));
            } else if ("Network.responseReceived".equals(method) && params != null) {
                JSONObject res = params.optJSONObject("response");
                if (res != null) appendNetwork("← " + res.optInt("status") + " "
                        + res.optString("url"));
            } else if (msg.has("id")) {
                JSONObject result = msg.optJSONObject("result");
                if (result == null) {
                    if (msg.has("error")) appendConsole("CDP ERROR: " + msg.optJSONObject("error"));
                    return;
                }
                JSONObject rootNode = result.optJSONObject("root");
                if (rootNode != null) {
                    StringBuilder tree = new StringBuilder();
                    printNode(rootNode, 0, tree);
                    String formatted = tree.toString();
                    main.post(() -> { elementsText = formatted; render(); });
                }
                JSONObject value = result.optJSONObject("result");
                if (value != null) {
                    appendConsole("= " + value.optString("value",
                            value.optString("description", "undefined")));
                }
                if (result.has("exceptionDetails")) {
                    appendConsole("Exception: " + result.optJSONObject("exceptionDetails"));
                }
            }
        } catch (JSONException ignored) { appendConsole("Unparsable CDP event"); }
    }

    private void printNode(JSONObject node, int level, StringBuilder out) {
        if (level > 8 || out.length() > 100000) return;
        for (int i = 0; i < level; i++) out.append("  ");
        out.append(node.optString("nodeName")).append("\n");
        JSONArray children = node.optJSONArray("children");
        if (children == null) return;
        for (int i = 0; i < children.length(); i++) {
            JSONObject child = children.optJSONObject(i);
            if (child != null) printNode(child, level + 1, out);
        }
    }

    private void appendConsole(String line) {
        main.post(() -> { trimAppend(consoleText, line); render(); });
    }

    private void appendNetwork(String line) {
        main.post(() -> { trimAppend(networkText, line); render(); });
    }

    private static void trimAppend(StringBuilder text, String line) {
        text.append(line).append('\n');
        if (text.length() > 32000) text.delete(0, text.length() - 22000);
    }

    private void render() {
        if (output == null) return;
        switch (selectedPanel) {
            case "Elements": output.setText(elementsText); break;
            case "Network": output.setText(networkText); break;
            default: output.setText(consoleText);
        }
    }

    private void setStatus(String message) {
        main.post(() -> { if (!isFinishing() && status != null) status.setText(message); });
    }

    private static LocalSocket openSocket() throws IOException {
        LocalSocket socket = new LocalSocket();
        try {
            socket.connect(new LocalSocketAddress(
                    SOCKET_NAME, LocalSocketAddress.Namespace.ABSTRACT));
            return socket;
        } catch (IOException error) {
            socket.close();
            throw error;
        }
    }

    private static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int matched = 0;
        while (matched < 4) {
            int n = in.read();
            if (n == -1) throw new EOFException("HTTP handshake ended early");
            if (buffer.size() >= 16384) throw new IOException("HTTP header too large");
            buffer.write(n);
            String ending = "\r\n\r\n";
            matched = (n == ending.charAt(matched)) ? matched + 1
                    : (n == '\r' ? 1 : 0);
        }
        return buffer.toString("US-ASCII");
    }

    @Override
    protected void onDestroy() {
        CdpClient old = client;
        if (old != null) old.close();
        executor.shutdownNow();
        super.onDestroy();
    }

    private final class CdpClient {
        private final String path;
        private final AtomicInteger ids = new AtomicInteger(1);
        private final Object sendLock = new Object();
        private final SecureRandom random = new SecureRandom();
        private volatile LocalSocket socket;
        private volatile OutputStream out;
        private volatile InputStream in;

        CdpClient(String path) { this.path = path; }

        void connect() throws Exception {
            LocalSocket connected = openSocket();
            try {
                connected.setSoTimeout(10000);
                InputStream reader = connected.getInputStream();
                OutputStream writer = connected.getOutputStream();
                byte[] nonce = new byte[16];
                random.nextBytes(nonce);
                String key = android.util.Base64.encodeToString(nonce, android.util.Base64.NO_WRAP);
                String request = "GET " + path + " HTTP/1.1\r\n"
                        + "Host: localhost\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n"
                        + "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: " + key + "\r\n\r\n";
                writer.write(request.getBytes(StandardCharsets.US_ASCII));
                writer.flush();
                String headers = readHeaders(reader);
                if (!headers.startsWith("HTTP/1.1 101")) {
                    throw new IOException("WebSocket upgrade denied: " + headers.split("\r\n")[0]);
                }
                String accepted = null;
                for (String line : headers.split("\r\n")) {
                    if (line.toLowerCase(Locale.ROOT).startsWith("sec-websocket-accept:")) {
                        accepted = line.substring(line.indexOf(':') + 1).trim();
                    }
                }
                byte[] hash = MessageDigest.getInstance("SHA-1")
                        .digest((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                        .getBytes(StandardCharsets.US_ASCII));
                String expected = android.util.Base64.encodeToString(
                        hash, android.util.Base64.NO_WRAP);
                if (!expected.equals(accepted)) throw new IOException("Invalid WebSocket handshake");
                connected.setSoTimeout(0);
                socket = connected;
                out = writer;
                in = reader;
            } catch (Exception e) {
                connected.close();
                throw e;
            }
        }

        void send(String method, JSONObject params) throws JSONException, IOException {
            JSONObject packet = new JSONObject()
                    .put("id", ids.getAndIncrement())
                    .put("method", method)
                    .put("params", params);
            byte[] payload = packet.toString().getBytes(StandardCharsets.UTF_8);
            writeFrame(1, payload);
        }

        private void writeFrame(int opcode, byte[] payload) throws IOException {
            synchronized (sendLock) {
                OutputStream writer = out;
                if (writer == null) throw new IOException("Not connected");
                writer.write(0x80 | opcode);
                if (payload.length < 126) writer.write(0x80 | payload.length);
                else if (payload.length <= 65535) {
                    writer.write(0x80 | 126);
                    writer.write((payload.length >>> 8) & 255);
                    writer.write(payload.length & 255);
                } else {
                    writer.write(0x80 | 127);
                    long length = payload.length;
                    for (int shift = 56; shift >= 0; shift -= 8)
                        writer.write((int) ((length >>> shift) & 255));
                }
                byte[] mask = new byte[4];
                random.nextBytes(mask);
                writer.write(mask);
                byte[] masked = payload.clone();
                for (int i = 0; i < masked.length; i++)
                    masked[i] ^= mask[i % 4];
                writer.write(masked);
                writer.flush();
            }
        }

        void readLoop() {
            ByteArrayOutputStream fragments = new ByteArrayOutputStream();
            try {
                while (!Thread.currentThread().isInterrupted()) {
                    InputStream reader = in;
                    if (reader == null) break;
                    int first = reader.read();
                    if (first == -1) break;
                    int second = mustRead(reader);
                    int opcode = first & 15;
                    boolean fin = (first & 0x80) != 0;
                    boolean masked = (second & 0x80) != 0;
                    long length = second & 127;
                    if (length == 126) length = (mustRead(reader) << 8) | mustRead(reader);
                    else if (length == 127) {
                        length = 0;
                        for (int i = 0; i < 8; i++) length = (length << 8) | mustRead(reader);
                    }
                    if (length < 0 || length > MAX_FRAME) throw new IOException("CDP message too large");
                    byte[] mask = new byte[4];
                    if (masked) readFully(reader, mask);
                    byte[] data = new byte[(int) length];
                    readFully(reader, data);
                    if (masked) for (int i = 0; i < data.length; i++) data[i] ^= mask[i % 4];

                    if (opcode == 8) break;
                    if (opcode == 9) { writeFrame(10, data); continue; }
                    if (opcode == 10) continue;
                    if (opcode == 1 || opcode == 0) {
                        if (fragments.size() + data.length > MAX_FRAME)
                            throw new IOException("CDP fragmented message too large");
                        fragments.write(data);
                        if (fin) {
                            String payload = fragments.toString("UTF-8");
                            fragments.reset();
                            handleMessage(payload);
                        }
                    }
                }
            } catch (IOException error) {
                if (client == this) setStatus("CDP disconnected: " + error.getMessage());
            } finally { close(); }
        }

        private int mustRead(InputStream reader) throws IOException {
            int n = reader.read();
            if (n == -1) throw new EOFException("WebSocket ended");
            return n;
        }

        private void readFully(InputStream reader, byte[] buffer) throws IOException {
            int pos = 0;
            while (pos < buffer.length) {
                int n = reader.read(buffer, pos, buffer.length - pos);
                if (n == -1) throw new EOFException("Incomplete WebSocket frame");
                pos += n;
            }
        }

        void close() {
            LocalSocket current = socket;
            socket = null;
            out = null;
            in = null;
            if (current != null) {
                try { current.close(); } catch (IOException ignored) {}
            }
        }
    }
}
