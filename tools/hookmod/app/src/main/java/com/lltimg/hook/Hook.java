package com.lltimg.hook;

import java.io.File;
import java.io.FileWriter;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage.LoadPackageParam;

/**
 * LSPosed 模块：hook 路路通(com.lltskb.lltskb)的 OkHttp 响应层，
 * 抓取 12306 车型接口(getCarDetail / trainStyle / queryTrainDiagram)的
 * 完整请求(含 URL + 全部 header + cookie/token)与响应 JSON，
 * 追加写入 App 内部 files 目录：/data/data/com.lltskb.lltskb/files/car_hook.log
 * 用 peekBody 读响应，不消费原 body，不影响 App 正常显示。
 */
public class Hook implements IXposedHookLoadPackage {

    private static final String TARGET = "com.lltskb.lltskb";
    private static final String LOG_PATH =
            "/data/data/com.lltskb.lltskb/files/car_hook.log";

    @Override
    public void handleLoadPackage(LoadPackageParam lpparam) {
        if (!TARGET.equals(lpparam.packageName)) return;

        write("===== 模块已加载，等待网络请求 =====");
        XposedBridge.log("[LltImgHook] loaded into " + lpparam.packageName);

        try {
            Class<?> builder = XposedHelpers.findClass(
                    "okhttp3.Response$Builder", lpparam.classLoader);

            XposedHelpers.findAndHookMethod(builder, "build", new XC_MethodHook() {
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    try {
                        Object resp = param.getResult();
                        if (resp == null) return;
                        Object req = XposedHelpers.callMethod(resp, "request");
                        Object urlObj = XposedHelpers.callMethod(req, "url");
                        String url = String.valueOf(
                                XposedHelpers.callMethod(urlObj, "toString"));
                        if (!match(url)) return;

                        // 图片请求：只记完整 URL（拿图床 base），不读二进制体
                        if (isImage(url)) {
                            write("[IMG] " + url);
                            return;
                        }

                        StringBuilder sb = new StringBuilder();
                        sb.append("\n======== [12306 命中] ").append(now()).append(" ========\n");
                        String method = String.valueOf(
                                XposedHelpers.callMethod(req, "method"));
                        sb.append(">>> ").append(method).append(' ').append(url).append('\n');

                        // 请求头（含 Cookie / token / 签名等）
                        Object reqHeaders = XposedHelpers.callMethod(req, "headers");
                        int rn = (int) XposedHelpers.callMethod(reqHeaders, "size");
                        for (int i = 0; i < rn; i++) {
                            String n = String.valueOf(
                                    XposedHelpers.callMethod(reqHeaders, "name", i));
                            String v = String.valueOf(
                                    XposedHelpers.callMethod(reqHeaders, "value", i));
                            sb.append("    ").append(n).append(": ").append(v).append('\n');
                        }

                        // 请求体（POST 时）
                        try {
                            Object body = XposedHelpers.callMethod(req, "body");
                            if (body != null) {
                                Object buffer = XposedHelpers.newInstance(
                                        XposedHelpers.findClass("okio.Buffer", lpparam.classLoader));
                                XposedHelpers.callMethod(body, "writeTo", buffer);
                                String bs = String.valueOf(
                                        XposedHelpers.callMethod(buffer, "readUtf8"));
                                sb.append("    [reqBody] ").append(bs).append('\n');
                            }
                        } catch (Throwable ignore) {}

                        // 响应码 + 响应体（peekBody 不消费）
                        int code = (int) XposedHelpers.callMethod(resp, "code");
                        sb.append("<<< HTTP ").append(code).append('\n');
                        try {
                            Object peek = XposedHelpers.callMethod(
                                    resp, "peekBody", 5L * 1024 * 1024);
                            String rb = String.valueOf(
                                    XposedHelpers.callMethod(peek, "string"));
                            sb.append("<<< [respBody] ").append(rb).append('\n');
                        } catch (Throwable e) {
                            sb.append("<<< peekBody 失败: ").append(e).append('\n');
                        }
                        sb.append("======== [end] ========\n");
                        write(sb.toString());
                    } catch (Throwable t) {
                        write("[hook inner err] " + t);
                    }
                }
            });
            write("[*] okhttp3.Response$Builder.build 已 hook");
        } catch (Throwable t) {
            write("[!] hook okhttp 失败: " + t);
            XposedBridge.log("[LltImgHook] hook failed: " + t);
        }

        // 图片走 Glide 的 HttpURLConnection：hook java.net.URL 构造函数抓图床
        try {
            XposedHelpers.findAndHookConstructor("java.net.URL", lpparam.classLoader,
                    String.class, new XC_MethodHook() {
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    try {
                        String u = String.valueOf(param.args[0]);
                        if (u != null && isImage(u)) write("[IMG] " + u);
                    } catch (Throwable ignore) {}
                }
            });
            write("[*] java.net.URL 构造 已 hook");
        } catch (Throwable t) {
            write("[!] hook URL 失败: " + t);
        }
    }

    private static boolean match(String u) {
        if (u == null) return false;
        // 图片请求：只记 URL 行(响应体是二进制，跳过 peekBody)，用于定位图床 base
        String low = u.toLowerCase();
        if (low.contains(".png") || low.contains(".jpg") || low.contains(".jpeg")
                || low.contains(".webp")) return true;
        return u.contains("getCarDetail") || u.contains("trainStyle")
                || u.contains("queryTrainDiagram") || u.contains("cateringimages")
                || u.contains("mobile.12306.cn");
    }

    private static boolean isImage(String u) {
        String low = u.toLowerCase();
        return low.contains(".png") || low.contains(".jpg")
                || low.contains(".jpeg") || low.contains(".webp");
    }

    private static String now() {
        return String.valueOf(System.currentTimeMillis());
    }

    private static synchronized void write(String s) {
        try {
            File f = new File(LOG_PATH);
            FileWriter w = new FileWriter(f, true);
            w.write(s);
            w.write("\n");
            w.close();
        } catch (Throwable ignore) {}
    }
}
