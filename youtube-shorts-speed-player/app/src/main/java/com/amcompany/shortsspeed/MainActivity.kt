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
import android.widget.FrameLayout
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.amcompany.shortsspeed.databinding.ActivityMainBinding
import com.google.android.material.chip.Chip

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var speedManager: SpeedControlManager
    private var webView: WebView? = null
    private var fullscreenView: View? = null
    private var fullscreenCallback: WebChromeClient.CustomViewCallback? = null

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
        setupSpeedChips()
        setupUrlInput()

        // Handle intent (shared URL)
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIntent(it) }
    }

    private fun handleIntent(intent: Intent) {
        val url = intent.dataString
            ?: intent.getStringExtra(Intent.EXTRA_TEXT)

        if (url != null && url.contains("shorts")) {
            binding.urlInput.setText(url)
            loadUrl(url)
        }
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

            // Enable cookies
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
                    // Inject speed after page loads
                    view?.let {
                        speedManager.injectSpeed(it)
                    }
                }

                override fun shouldOverrideUrlLoading(
                    view: WebView?,
                    request: WebResourceRequest?
                ): Boolean {
                    val url = request?.url?.toString() ?: return false
                    // Keep YouTube navigation in WebView
                    if (url.contains("youtube.com") || url.contains("youtu.be")) {
                        return false
                    }
                    // Open external links in browser
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

    private fun setupSpeedChips() {
        val chipGroup = binding.speedChipGroup
        chipGroup.removeAllViews()

        SpeedControlManager.SPEEDS.forEach { speed ->
            val chip = Chip(this).apply {
                text = speedManager.formatSpeed(speed)
                isCheckable = true
                isChecked = speed == speedManager.currentSpeed
                setOnClickListener {
                    speedManager.setSpeed(webView, speed)
                    updateChipSelection(speed)
                }
            }
            chipGroup.addView(chip)
        }

        speedManager.onSpeedChanged = { speed ->
            updateChipSelection(speed)
        }
    }

    private fun updateChipSelection(selectedSpeed: Float) {
        val chipGroup = binding.speedChipGroup
        SpeedControlManager.SPEEDS.forEachIndexed { index, speed ->
            val chip = chipGroup.getChildAt(index) as? Chip
            chip?.isChecked = speed == selectedSpeed
        }
    }

    private fun setupUrlInput() {
        binding.btnGo.setOnClickListener {
            val url = binding.urlInput.text?.toString()?.trim() ?: ""
            if (url.isNotEmpty()) {
                val finalUrl = normalizeUrl(url)
                loadUrl(finalUrl)
            }
        }

        binding.btnBrowse.setOnClickListener {
            binding.urlInput.setText("")
            loadUrl(SHORTS_BASE_URL)
        }

        // Load shorts feed by default
        loadUrl(SHORTS_BASE_URL)
    }

    private fun normalizeUrl(input: String): String {
        if (input.startsWith("http://") || input.startsWith("https://")) {
            return input
        }
        return "https://$input"
    }

    private fun loadUrl(url: String) {
        webView?.loadUrl(url)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        when {
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
