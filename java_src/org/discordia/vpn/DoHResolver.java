/*
 * DNS-over-HTTPS resolver using Cloudflare 1.1.1.1
 * Used as a fallback/alternative to raw UDP DNS.
 */

package org.discordia.vpn;

import android.util.Log;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Base64;

public class DoHResolver {

    private static final String TAG = "DiscordiaDoH";
    private static final String DOH_URL =
        "https://cloudflare-dns.com/dns-query";

    /**
     * Resolve a DNS query via DoH (POST method — RFC 8484).
     *
     * @param dnsQuery  Raw DNS query bytes
     * @return          Raw DNS response bytes, or null on error
     */
    public static byte[] resolve(byte[] dnsQuery) {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(DOH_URL);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty(
                "Content-Type", "application/dns-message"
            );
            conn.setRequestProperty(
                "Accept", "application/dns-message"
            );
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(5000);
            conn.setDoOutput(true);

            OutputStream os = conn.getOutputStream();
            os.write(dnsQuery);
            os.flush();
            os.close();

            int code = conn.getResponseCode();
            if (code != 200) {
                Log.w(TAG, "DoH response code: " + code);
                return null;
            }

            InputStream is = conn.getInputStream();
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[1024];
            int read;
            while ((read = is.read(chunk)) != -1) {
                buffer.write(chunk, 0, read);
            }
            is.close();

            return buffer.toByteArray();

        } catch (Exception e) {
            Log.e(TAG, "DoH resolve error", e);
            return null;
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    /**
     * Resolve via DoH GET method (for simpler queries).
     *
     * @param dnsQuery  Raw DNS query bytes
     * @return          Raw DNS response bytes, or null
     */
    public static byte[] resolveGet(byte[] dnsQuery) {
        HttpURLConnection conn = null;
        try {
            String encoded;
            if (android.os.Build.VERSION.SDK_INT >= 26) {
                encoded = Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(dnsQuery);
            } else {
                encoded = android.util.Base64.encodeToString(
                    dnsQuery,
                    android.util.Base64.URL_SAFE
                        | android.util.Base64.NO_PADDING
                        | android.util.Base64.NO_WRAP
                );
            }

            URL url = new URL(DOH_URL + "?dns=" + encoded);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setRequestProperty(
                "Accept", "application/dns-message"
            );
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(5000);

            int code = conn.getResponseCode();
            if (code != 200) return null;

            InputStream is = conn.getInputStream();
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[1024];
            int read;
            while ((read = is.read(chunk)) != -1) {
                buffer.write(chunk, 0, read);
            }
            is.close();

            return buffer.toByteArray();

        } catch (Exception e) {
            Log.e(TAG, "DoH GET error", e);
            return null;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }
}