package io.github.tomneverwinter.hapip;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.Base64;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.DateFormat;
import java.util.Arrays;
import java.util.Date;
import java.util.HashSet;
import java.util.Set;

/**
 * LAN listener: POST /notify (JSON) from an allow-listed IP with "Authorization: Bearer <token>"
 * shows image + camera/location + timestamp + optional AI analysis in a corner overlay.
 * Nothing is stored and nothing is fetched: the image arrives inline as base64.
 */
public class OverlayService extends Service {
    static final String TAG = "HaPip";
    static final int PORT = 7979;
    static final int MAX_BODY = 8 << 20;
    static final int MAX_LINE = 8192;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Runnable hide = this::hide;
    private volatile ServerSocket server;
    private View shown;

    static SharedPreferences prefs(Context ctx) {
        return ctx.getSharedPreferences("config", MODE_PRIVATE);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel("svc", "Listener", NotificationManager.IMPORTANCE_MIN));
        Notification n = new Notification.Builder(this, "svc")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle("HA PiP Notifications listening")
                .build();
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(1, n);
        new Thread(this::serve, "hapip-http").start();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        try {
            if (server != null) server.close();
        } catch (IOException ignored) {
        }
        ui.post(hide);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    // ponytail: one request at a time with a 5 s socket timeout; HA sends a handful per event.
    private void serve() {
        try (ServerSocket s = new ServerSocket(PORT)) {
            server = s;
            while (!s.isClosed()) {
                try (Socket c = s.accept()) {
                    handle(c);
                } catch (Exception | OutOfMemoryError e) { // one bad request must not kill the listener
                    if (s.isClosed()) break;
                    Log.w(TAG, "request failed: " + e);
                }
            }
        } catch (IOException e) {
            Log.e(TAG, "listener stopped: " + e);
        }
    }

    private void handle(Socket c) throws Exception {
        c.setSoTimeout(5000);
        OutputStream out = c.getOutputStream();
        SharedPreferences p = prefs(this);
        String token = p.getString("token", "");
        String ip = c.getInetAddress().getHostAddress();
        if (token.isEmpty() || !allowed(p.getString("allow", "")).contains(ip)) {
            Log.w(TAG, "rejected " + ip);
            reply(out, 403, "forbidden");
            return;
        }

        InputStream in = new BufferedInputStream(c.getInputStream());
        String request = readLine(in);
        if (request == null) return;
        int len = -1;
        String auth = "";
        for (int i = 0; i < 100; i++) {
            String h = readLine(in);
            if (h == null || h.isEmpty()) break;
            int colon = h.indexOf(':');
            if (colon < 0) continue;
            String name = h.substring(0, colon).trim().toLowerCase();
            String value = h.substring(colon + 1).trim();
            if (name.equals("content-length")) len = Integer.parseInt(value);
            else if (name.equals("authorization")) auth = value;
        }

        if (!request.startsWith("POST /notify ")) {
            reply(out, 404, "not found");
            return;
        }
        if (!MessageDigest.isEqual(("Bearer " + token).getBytes(StandardCharsets.UTF_8),
                auth.getBytes(StandardCharsets.UTF_8))) {
            Log.w(TAG, "bad token from " + ip);
            reply(out, 401, "unauthorized");
            return;
        }
        if (len <= 0 || len > MAX_BODY) {
            reply(out, 413, "bad length");
            return;
        }

        byte[] body = new byte[len];
        for (int off = 0; off < len; ) {
            int r = in.read(body, off, len - off);
            if (r < 0) throw new IOException("short body");
            off += r;
        }

        Popup pop;
        try {
            pop = Popup.parse(new JSONObject(new String(body, StandardCharsets.UTF_8)));
        } catch (Exception e) {
            reply(out, 400, "bad json");
            return;
        }
        ui.post(() -> show(pop));
        reply(out, 200, "ok");
    }

    static Set<String> allowed(String csv) {
        Set<String> s = new HashSet<>();
        for (String a : csv.split(",")) if (!a.trim().isEmpty()) s.add(a.trim());
        return s;
    }

    static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int ch;
        while ((ch = in.read()) != -1 && ch != '\n') {
            if (b.size() >= MAX_LINE) throw new IOException("line too long");
            if (ch != '\r') b.write(ch);
        }
        return ch == -1 && b.size() == 0 ? null : b.toString("UTF-8");
    }

    static void reply(OutputStream out, int code, String msg) throws IOException {
        byte[] b = msg.getBytes(StandardCharsets.UTF_8);
        out.write(("HTTP/1.1 " + code + " " + msg + "\r\nContent-Type: text/plain\r\nContent-Length: "
                + b.length + "\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(b);
        out.flush();
    }

    static final class Popup {
        String camera, location, timestamp, analysis;
        int seconds;
        Bitmap image;

        static Popup parse(JSONObject j) {
            Popup p = new Popup();
            p.camera = j.optString("camera", "Camera");
            p.location = j.optString("location", "");
            p.timestamp = j.optString("timestamp", "");
            if (p.timestamp.isEmpty()) p.timestamp = DateFormat.getDateTimeInstance().format(new Date());
            p.analysis = j.optString("analysis", "");
            p.seconds = Math.max(3, Math.min(120, j.optInt("duration", 5)));
            String img = j.optString("image", "");
            if (!img.isEmpty()) {
                byte[] raw = Base64.decode(img, Base64.DEFAULT);
                BitmapFactory.Options o = new BitmapFactory.Options();
                o.inJustDecodeBounds = true;
                BitmapFactory.decodeByteArray(raw, 0, raw.length, o);
                o.inJustDecodeBounds = false;
                // Subsample on the larger side so a small file can't demand a huge bitmap.
                int side = Math.max(o.outWidth, o.outHeight);
                while (side / Math.max(1, o.inSampleSize) > 1920) o.inSampleSize = Math.max(2, o.inSampleSize * 2);
                p.image = BitmapFactory.decodeByteArray(raw, 0, raw.length, o);
            }
            return p;
        }
    }

    private void show(Popup p) {
        hide();
        // At most a quarter of the screen: half the width by half the height.
        android.util.DisplayMetrics dm = getResources().getDisplayMetrics();
        int maxW = dm.widthPixels / 2, maxH = dm.heightPixels / 2;
        int w = Math.min(px(400), maxW - px(28));
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setBackgroundColor(Color.argb(225, 10, 12, 16));
        box.setPadding(px(14), px(14), px(14), px(14));

        if (p.image != null) {
            ImageView iv = new ImageView(this);
            iv.setImageBitmap(p.image);
            iv.setAdjustViewBounds(true);
            iv.setMaxHeight(maxH * 6 / 10); // leave room for the text lines
            box.addView(iv, new LinearLayout.LayoutParams(w, LinearLayout.LayoutParams.WRAP_CONTENT));
        }
        String title = p.location.isEmpty() ? p.camera : p.camera + " · " + p.location;
        box.addView(text(title, 18, Color.WHITE, true, w, 1));
        box.addView(text(p.timestamp, 14, Color.rgb(170, 180, 190), false, w, 1));
        if (!p.analysis.isEmpty()) box.addView(text(p.analysis, 14, Color.rgb(230, 235, 240), false, w, 2));

        box.measure(View.MeasureSpec.makeMeasureSpec(maxW, View.MeasureSpec.AT_MOST),
                View.MeasureSpec.makeMeasureSpec(maxH, View.MeasureSpec.AT_MOST));
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                Math.min(box.getMeasuredWidth(), maxW), Math.min(box.getMeasuredHeight(), maxH),
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.END;
        lp.x = px(32);
        lp.y = px(32);
        try {
            getSystemService(WindowManager.class).addView(box, lp);
            shown = box;
            ui.postDelayed(hide, p.seconds * 1000L);
        } catch (Exception e) {
            Log.e(TAG, "overlay failed (grant SYSTEM_ALERT_WINDOW?): " + e);
        }
    }

    private void hide() {
        ui.removeCallbacks(hide);
        if (shown != null) {
            getSystemService(WindowManager.class).removeView(shown);
            shown = null;
        }
    }

    private TextView text(String s, int sp, int color, boolean bold, int maxWidth, int lines) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setMaxLines(lines);
        t.setEllipsize(android.text.TextUtils.TruncateAt.END);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setMaxWidth(maxWidth);
        t.setPadding(0, px(6), 0, 0);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    private int px(int dp) {
        return Math.round(dp * getResources().getDisplayMetrics().density);
    }
}
