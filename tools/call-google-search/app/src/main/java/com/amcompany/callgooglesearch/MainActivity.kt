package com.amcompany.callgooglesearch

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {

    private val requiredPermissions = arrayOf(
        Manifest.permission.READ_PHONE_STATE,
        Manifest.permission.READ_CALL_LOG
    )

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
