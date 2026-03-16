package com.amcompany.callgooglesearch

import android.content.Context

object PreferenceHelper {
    private const val PREF_NAME = "call_search_prefs"
    private const val KEY_ENABLED = "feature_enabled"

    fun isEnabled(context: Context): Boolean {
        return context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_ENABLED, false)
    }

    fun setEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_ENABLED, enabled)
            .apply()
    }
}
