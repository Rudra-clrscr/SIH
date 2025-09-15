import threading
from kivy.utils import platform

# --- IMPORT YOUR FLASK APP'S RUN FUNCTION ---
from app import run_server 

# --- Start Flask server in a single background thread ---
# This now runs only once when the script starts.
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# --- Main Execution Block ---
if __name__ == '__main__':
    
    # --- On Desktop, run pywebview ---
    if platform in ('win', 'linux', 'macosx'):
        import webview
        # The server is already running in the background thread.
        # We just need to create the window.
        url = 'http://127.0.0.1:5000' 
        webview.create_window('Smart Tourist Safety', url)
        webview.start()
    
    # --- On Android, run the Kivy App ---
    elif platform == 'android':
        from kivy.app import App
        from kivy.uix.label import Label
        from kivy.core.window import Window
        
        try:
            from jnius import autoclass, JavaException
            WebView = autoclass('android.webkit.WebView')
            WebViewClient = autoclass('android.webkit.WebViewClient')
            Activity = autoclass('org.kivy.android.PythonActivity')
        except (ImportError, JavaException):
            WebView = None # Will be None if not on Android

        class WebApp(App):
            def build(self):
                # 10.0.2.2 is the special IP for the host machine from the Android emulator
                self.url = 'http://10.0.2.2:5000' 
                
                if WebView:
                    self.activity = Activity.mActivity
                    self.webview = WebView(self.activity)
                    self.webview.setWebViewClient(WebViewClient())
                    self.webview.getSettings().setJavaScriptEnabled(True)
                    Window.bind(on_resize=self.on_window_resize)
                    self.activity.setContentView(self.webview)
                    self.webview.loadUrl(self.url)
                    # This Kivy Label is just a placeholder; the native WebView is what you'll see.
                    return Label(text="Loading WebView...") 
                
                return Label(text="This app is intended for Android.")

            def on_window_resize(self, window, width, height):
                if hasattr(self, 'webview'):
                    self.webview.layout(0, 0, width, height)

        WebApp().run()