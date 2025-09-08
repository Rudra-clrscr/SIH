import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.utils import platform

# --- WebView for Android ---
if platform == 'android':
    from jnius import autoclass
    from android.webkit import WebView, WebViewClient

kivy.require('2.1.0')

# Use 10.0.2.2 for Android emulator to connect to localhost of the host machine
HOME_URL = "http://10.0.2.2:5000" if platform == 'android' else "http://127.0.0.1:5000"

class WebViewApp(App):
    def build(self):
        layout = BoxLayout()
        if platform == 'android':
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            webview = WebView(activity)
            webview.setWebViewClient(WebViewClient())
            webview.getSettings().setJavaScriptEnabled(True)
            webview.getSettings().setDomStorageEnabled(True) # Important for some web apps
            layout.add_widget(webview)
            webview.loadUrl(HOME_URL)
        else:
            from kivy.uix.label import Label
            layout.add_widget(Label(text="This app is designed to run on Android.\nPlease open http://127.0.0.1:5000 in your desktop browser."))
            
        return layout

if __name__ == '__main__':
    WebViewApp().run()