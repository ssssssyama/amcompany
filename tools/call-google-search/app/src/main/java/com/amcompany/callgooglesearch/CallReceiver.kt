package com.amcompany.callgooglesearch

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.telephony.TelephonyManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

class CallReceiver : BroadcastReceiver() {

    companion object {
        const val CHANNEL_ID = "call_search_channel"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != TelephonyManager.ACTION_PHONE_STATE_CHANGED) return
        if (!PreferenceHelper.isEnabled(context)) return

        val state = intent.getStringExtra(TelephonyManager.EXTRA_STATE) ?: return
        if (state != TelephonyManager.EXTRA_STATE_RINGING) return

        val phoneNumber = intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER)
            ?: return

        val searchUrl = "https://www.google.com/search?q=${Uri.encode(phoneNumber)}"
        val pendingIntent = PendingIntent.getActivity(
            context,
            phoneNumber.hashCode(),
            Intent(Intent.ACTION_VIEW, Uri.parse(searchUrl)),
            PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_search)
            .setContentTitle(phoneNumber)
            .setContentText(context.getString(R.string.notification_text))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()

        try {
            NotificationManagerCompat.from(context)
                .notify(phoneNumber.hashCode(), notification)
        } catch (_: SecurityException) {
            // POST_NOTIFICATIONS permission not granted
        }
    }
}
