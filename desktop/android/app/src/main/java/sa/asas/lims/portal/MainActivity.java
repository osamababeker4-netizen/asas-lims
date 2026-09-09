package sa.asas.lims.portal;
import android.app.*;
import android.os.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.webkit.*;
import android.widget.*;
import android.view.*;
import android.print.*;
public class MainActivity extends Activity {
 private WebView web;
 private ValueCallback<Uri[]> chooser;
 private GeolocationPermissions.Callback locationCallback;
 private String locationOrigin;
 private static final String HOME="https://osamababeker4-netizen.github.io/asas-lims/?release=8-1-0";
 private boolean trusted(Uri uri){return "https".equals(uri.getScheme())&&"osamababeker4-netizen.github.io".equals(uri.getHost())&&uri.getPath()!=null&&uri.getPath().startsWith("/asas-lims/");}
 private void external(String url){Uri uri=Uri.parse(url);if(!java.util.Arrays.asList("https","mailto","tel").contains(uri.getScheme()))return;try{startActivity(new Intent(Intent.ACTION_VIEW,uri));}catch(ActivityNotFoundException e){Toast.makeText(this,"No app available / لا يوجد تطبيق مناسب",Toast.LENGTH_LONG).show();}}
 @Override public void onCreate(Bundle state){
  super.onCreate(state);
  LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
  root.setOnApplyWindowInsetsListener((view,insets)->{view.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;});
  LinearLayout bar=new LinearLayout(this);
  Button home=new Button(this);home.setText("ASAS LIMS");home.setOnClickListener(v->web.loadUrl(HOME));bar.addView(home);
  Button reload=new Button(this);reload.setText("↻");reload.setContentDescription("Reload");reload.setOnClickListener(v->web.reload());bar.addView(reload);
  Button print=new Button(this);print.setText("Print / طباعة");print.setOnClickListener(v->{PrintManager manager=(PrintManager)getSystemService(PRINT_SERVICE);manager.print("ASAS LIMS",web.createPrintDocumentAdapter("ASAS LIMS"),new PrintAttributes.Builder().build());});bar.addView(print);
  root.addView(bar);web=new WebView(this);root.addView(web,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
  WebSettings settings=web.getSettings();settings.setJavaScriptEnabled(true);settings.setDomStorageEnabled(true);settings.setAllowFileAccess(false);settings.setAllowContentAccess(true);settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);settings.setSupportMultipleWindows(false);
  CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
  web.setWebViewClient(new WebViewClient(){
   @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){Uri uri=request.getUrl();if(trusted(uri)&&!uri.getPath().endsWith(".pdf"))return false;external(uri.toString());return true;}
   @Override public void onReceivedError(WebView view,WebResourceRequest req,WebResourceError err){if(req.isForMainFrame())Toast.makeText(MainActivity.this,"Check connection and reload / تحقق من الاتصال وأعد التحميل",Toast.LENGTH_LONG).show();}
  });
  web.setWebChromeClient(new WebChromeClient(){
   @Override public boolean onShowFileChooser(WebView view,ValueCallback<Uri[]> callback,FileChooserParams params){if(chooser!=null)chooser.onReceiveValue(null);chooser=callback;try{startActivityForResult(params.createIntent(),100);return true;}catch(ActivityNotFoundException e){chooser=null;return false;}}
   @Override public void onGeolocationPermissionsShowPrompt(String origin,GeolocationPermissions.Callback callback){if(!"https://osamababeker4-netizen.github.io".equals(origin.replaceAll("/$",""))){callback.invoke(origin,false,false);return;}if(checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED){callback.invoke(origin,true,false);return;}locationCallback=callback;locationOrigin=origin;requestPermissions(new String[]{android.Manifest.permission.ACCESS_FINE_LOCATION,android.Manifest.permission.ACCESS_COARSE_LOCATION},101);}
  });
  web.setDownloadListener((url,agent,disposition,mime,length)->external(url));
  if(state==null)web.loadUrl(HOME);else web.restoreState(state);
 }
 @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request==100&&chooser!=null){chooser.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result,data));chooser=null;}}
 @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){super.onRequestPermissionsResult(request,permissions,results);if(request==101&&locationCallback!=null){boolean allowed=false;for(int result:results)allowed|=result==PackageManager.PERMISSION_GRANTED;locationCallback.invoke(locationOrigin,allowed,false);locationCallback=null;}}
 @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
 @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);web.saveState(state);}
 @Override protected void onDestroy(){if(chooser!=null)chooser.onReceiveValue(null);if(web!=null)web.destroy();super.onDestroy();}
}
