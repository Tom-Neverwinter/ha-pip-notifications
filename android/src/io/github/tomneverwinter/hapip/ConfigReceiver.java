package io.github.tomneverwinter.hapip;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

/**
 * Boot/update starter and adb-only config:
 * adb shell am broadcast -f 32 -n io.github.tomneverwinter.hapip/.ConfigReceiver --es token T --es allow HA_IP
 */
public class ConfigReceiver extends BroadcastReceiver {
    static final int MIN_TOKEN = 16;

    @Override
    @android.annotation.SuppressLint("ApplySharedPref") // commit() is deliberate, see below
    public void onReceive(Context ctx, Intent i) {
        // Config only from an explicit, action-less adb broadcast; boot/update just (re)start the listener.
        if (i.getAction() == null) {
            SharedPreferences.Editor e = OverlayService.prefs(ctx).edit();
            String token = i.getStringExtra("token");
            if (token != null) {
                if (token.length() < MIN_TOKEN) Log.w(OverlayService.TAG, "token too short, ignored");
                else e.putString("token", token);
            }
            String allow = i.getStringExtra("allow");
            if (allow != null) e.putString("allow", allow);
            e.commit(); // synchronous on purpose: must be on disk before the listener reads it
        } else if (!Intent.ACTION_BOOT_COMPLETED.equals(i.getAction())
                && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(i.getAction())) {
            return;
        }
        ctx.startForegroundService(new Intent(ctx, OverlayService.class));
    }
}
