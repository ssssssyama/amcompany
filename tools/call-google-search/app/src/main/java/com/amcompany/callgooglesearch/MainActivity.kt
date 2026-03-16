package com.amcompany.callgooglesearch

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {

    private val requiredPermissions = buildList {
        add(Manifest.permission.READ_PHONE_STATE)
        add(Manifest.permission.READ_CALL_LOG)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            add(Manifest.permission.POST_NOTIFICATIONS)
        }
    }.toTypedArray()

    private lateinit var featureSwitch: SwitchCompat
    private lateinit var statusText: TextView
    private lateinit var openSettingsButton: Button

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        updateUiState(results.values.all { it })
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        createNotificationChannel()

        featureSwitch = findViewById(R.id.featureSwitch)
        statusText = findViewById(R.id.statusText)
        openSettingsButton = findViewById(R.id.openSettingsButton)

        featureSwitch.isChecked = PreferenceHelper.isEnabled(this)
        featureSwitch.setOnCheckedChangeListener { _, isChecked ->
            PreferenceHelper.setEnabled(this, isChecked)
            updateStatusText()
        }

        openSettingsButton.setOnClickListener {
            val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.fromParts("package", packageName, null)
            }
            startActivity(intent)
        }

        if (!hasPermissions()) {
            permissionLauncher.launch(requiredPermissions)
        }
    }

    override fun onResume() {
        super.onResume()
        updateUiState(hasPermissions())
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CallReceiver.CHANNEL_ID,
            getString(R.string.channel_name),
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = getString(R.string.channel_description)
        }
        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.createNotificationChannel(channel)
    }

    private fun hasPermissions(): Boolean =
        requiredPermissions.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }

    private fun updateUiState(permissionsGranted: Boolean) {
        featureSwitch.isEnabled = permissionsGranted
        openSettingsButton.visibility = if (permissionsGranted) {
            android.view.View.GONE
        } else {
            android.view.View.VISIBLE
        }

        if (!permissionsGranted) {
            featureSwitch.isChecked = false
            PreferenceHelper.setEnabled(this, false)
        }

        updateStatusText()
    }

    private fun updateStatusText() {
        statusText.text = when {
            !hasPermissions() -> getString(R.string.permissions_required)
            PreferenceHelper.isEnabled(this) -> getString(R.string.status_enabled)
            else -> getString(R.string.status_disabled)
        }
    }
}
