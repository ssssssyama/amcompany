package com.amcompany.shortsspeed

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import com.amcompany.shortsspeed.databinding.ActivityMainBinding
import com.google.android.material.chip.Chip

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var speedManager: SpeedControlManager
    private var webView: WebView? = null
    private var fullscreenView: View? = null
    private var fullscreenCallback: WebChromeClient.CustomViewCallback? = null
    private var speedPanelVisible = false

    companion object {
        private const val SHORTS_BASE_URL = "https://www.youtube.com/shorts"
        private const val DESKTOP_USER_AGENT =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        speedManager = SpeedControlManager()

        setupWebView()
        setupSpeedControls()

        // Handle intent or load default
        if (!handleIntent(intent)) {
            loadUrl(SHORTS_BASE_URL)
        }
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIntent(it) }
    }

    private fun handleIntent(intent: Intent): Boolean {
        val url = intent.dataString
            ?: intent.getStringExtra(Intent.EXTRA_TEXT)

        if (url != null && url.contains("shorts")) {
            loadUrl(url)
            return true
        }
        return false
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView = binding.webView

        webView?.apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.userAgentString = DESKTOP_USER_AGENT
            settings.loadWithOverviewMode = true
            settings.useWideViewPort = true
            settings.setSupportZoom(false)

            CookieManager.getInstance().setAcceptCookie(true)
            CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)

            webViewClient = object : WebViewClient() {
                override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                    super.onPageStarted(view, url, favicon)
                    binding.progressBar.visibility = View.VISIBLE
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    binding.progressBar.visibility = View.GONE
                    view?.let { speedManager.injectSpeed(it) }
                }

                override fun shouldOverrideUrlLoading(
                    view: WebView?,
                    request: WebResourceRequest?
                ): Boolean {
                    val url = request?.url?.toString() ?: return false
                    if (url.contains("youtube.com") || url.contains("youtu.be")) {
                        return false
                    }
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                    return true
                }
            }

            webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(view: WebView?, newProgress: Int) {
                    binding.progressBar.progress = newProgress
                }

                override fun onShowCustomView(view: View?, callback: CustomViewCallback?) {
                    fullscreenView = view
                    fullscreenCallback = callback
                    binding.fullscreenContainer.addView(view)
                    binding.fullscreenContainer.visibility = View.VISIBLE
                    binding.mainContent.visibility = View.GONE
                }

                override fun onHideCustomView() {
                    binding.fullscreenContainer.removeAllViews()
                    binding.fullscreenContainer.visibility = View.GONE
                    binding.mainContent.visibility = View.VISIBLE
                    fullscreenCallback?.onCustomViewHidden()
                    fullscreenView = null
                    fullscreenCallback = null
                }
            }
        }
    }

    private fun setupSpeedControls() {
        // Floating button toggles speed panel
        binding.btnSpeedToggle.setOnClickListener {
            toggleSpeedPanel()
        }

        // Build speed chips
        val chipGroup = binding.speedChipGroup
        chipGroup.removeAllViews()

        SpeedControlManager.SPEEDS.forEach { speed ->
            val chip = Chip(this).apply {
                text = speedManager.formatSpeed(speed)
                isCheckable = true
                isChecked = speed == speedManager.currentSpeed
                setOnClickListener {
                    speedManager.setSpeed(webView, speed)
                    updateSpeedUI(speed)
                    // Auto-close panel after selection
                    hideSpeedPanel()
                }
            }
            chipGroup.addView(chip)
        }

        speedManager.onSpeedChanged = { speed ->
            updateSpeedUI(speed)
        }
    }

    private fun toggleSpeedPanel() {
        if (speedPanelVisible) {
            hideSpeedPanel()
        } else {
            showSpeedPanel()
        }
    }

    private fun showSpeedPanel() {
        binding.speedPanel.visibility = View.VISIBLE
        binding.speedPanel.animate().alpha(0.92f).setDuration(150).start()
        speedPanelVisible = true
    }

    private fun hideSpeedPanel() {
        binding.speedPanel.animate().alpha(0f).setDuration(150).withEndAction {
            binding.speedPanel.visibility = View.GONE
        }.start()
        speedPanelVisible = false
    }

    private fun updateSpeedUI(speed: Float) {
        binding.btnSpeedToggle.text = speedManager.formatSpeed(speed)
        val chipGroup = binding.speedChipGroup
        SpeedControlManager.SPEEDS.forEachIndexed { index, s ->
            val chip = chipGroup.getChildAt(index) as? Chip
            chip?.isChecked = s == speed
        }
    }

    private fun loadUrl(url: String) {
        webView?.loadUrl(url)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        when {
            speedPanelVisible -> hideSpeedPanel()
            fullscreenView != null -> {
                fullscreenCallback?.onCustomViewHidden()
                binding.fullscreenContainer.removeAllViews()
                binding.fullscreenContainer.visibility = View.GONE
                binding.mainContent.visibility = View.VISIBLE
                fullscreenView = null
                fullscreenCallback = null
            }
            webView?.canGoBack() == true -> webView?.goBack()
            else -> super.onBackPressed()
        }
    }

    override fun onResume() {
        super.onResume()
        webView?.onResume()
    }

    override fun onPause() {
        webView?.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        webView?.let {
            it.stopLoading()
            (it.parent as? ViewGroup)?.removeView(it)
            it.destroy()
        }
        webView = null
        super.onDestroy()
    }
}
