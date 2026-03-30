package com.amcompany.shortsspeed

import android.webkit.WebView

class SpeedControlManager {

    companion object {
        val SPEEDS = listOf(0.5f, 0.75f, 1.0f, 1.25f, 1.5f, 2.0f, 3.0f)
        const val DEFAULT_SPEED = 1.0f
    }

    var currentSpeed: Float = DEFAULT_SPEED
        private set

    var onSpeedChanged: ((Float) -> Unit)? = null

    fun setSpeed(webView: WebView?, speed: Float) {
        currentSpeed = speed
        webView?.let { injectSpeed(it, speed) }
        onSpeedChanged?.invoke(speed)
    }

    fun injectSpeed(webView: WebView, speed: Float = currentSpeed) {
        val js = """
            (function() {
                var speed = $speed;

                // Apply speed to all existing videos
                var videos = document.querySelectorAll('video');
                for (var i = 0; i < videos.length; i++) {
                    videos[i].playbackRate = speed;
                }

                // Store target speed globally
                window._targetSpeed = speed;

                // Remove previous observer if exists
                if (window._speedObserver) {
                    window._speedObserver.disconnect();
                }

                // MutationObserver to catch dynamically loaded videos
                window._speedObserver = new MutationObserver(function(mutations) {
                    var vids = document.querySelectorAll('video');
                    for (var i = 0; i < vids.length; i++) {
                        if (vids[i].playbackRate !== window._targetSpeed) {
                            vids[i].playbackRate = window._targetSpeed;
                        }
                    }
                });
                window._speedObserver.observe(document.body, {
                    childList: true,
                    subtree: true
                });

                // Also listen for play events to re-apply speed
                document.addEventListener('play', function(e) {
                    if (e.target && e.target.tagName === 'VIDEO') {
                        e.target.playbackRate = window._targetSpeed;
                    }
                }, true);

                // Periodic check as fallback
                if (window._speedInterval) clearInterval(window._speedInterval);
                window._speedInterval = setInterval(function() {
                    var vids = document.querySelectorAll('video');
                    for (var i = 0; i < vids.length; i++) {
                        if (vids[i].playbackRate !== window._targetSpeed) {
                            vids[i].playbackRate = window._targetSpeed;
                        }
                    }
                }, 1000);
            })();
        """.trimIndent()

        webView.evaluateJavascript(js, null)
    }

    fun formatSpeed(speed: Float): String {
        return if (speed == speed.toLong().toFloat()) {
            "${speed.toLong()}x"
        } else {
            "${speed}x"
        }
    }
}
