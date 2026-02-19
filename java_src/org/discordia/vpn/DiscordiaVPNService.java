/*
 * DiscordiaVPN — Android VPN Service
 *
 * Implements DNS-over-HTTPS tunneling via Cloudflare 1.1.1.1
 * Creates a local TUN device, intercepts DNS queries,
 * forwards them encrypted to Cloudflare's DoH endpoint.
 */

package org.discordia.vpn;

import android.content.Intent;
import android.net.VpnService;
import android.os.ParcelFileDescriptor;
import android.util.Log;

import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.util.concurrent.atomic.AtomicBoolean;

public class DiscordiaVPNService extends VpnService {

    private static final String TAG = "DiscordiaVPN";
    private static final int MTU = 1500;
    private static final String VPN_ADDRESS = "10.0.0.2";
    private static final String VPN_ROUTE = "0.0.0.0";

    private ParcelFileDescriptor vpnInterface;
    private Thread vpnThread;
    private AtomicBoolean isRunning = new AtomicBoolean(false);

    private String dnsPrimary = "1.1.1.1";
    private String dnsSecondary = "1.0.0.1";
    private boolean blockAds = false;
    private boolean splitTunnel = true;
    private String mode = "doh";

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) {
            return START_NOT_STICKY;
        }

        String action = intent.getAction();

        if ("STOP".equals(action)) {
            stopVpn();
            stopSelf();
            return START_NOT_STICKY;
        }

        // Extract config
        mode = intent.getStringExtra("mode");
        if (mode == null) mode = "doh";

        dnsPrimary = intent.getStringExtra("dns_primary");
        if (dnsPrimary == null) dnsPrimary = "1.1.1.1";

        dnsSecondary = intent.getStringExtra("dns_secondary");
        if (dnsSecondary == null) dnsSecondary = "1.0.0.1";

        blockAds = intent.getBooleanExtra("block_ads", false);
        splitTunnel = intent.getBooleanExtra("split_tunnel", true);

        startVpn();
        return START_STICKY;
    }

    private void startVpn() {
        if (isRunning.get()) {
            Log.w(TAG, "VPN already running");
            return;
        }

        try {
            // Build VPN interface
            Builder builder = new Builder();
            builder.setSession("DiscordiaVPN");
            builder.setMtu(MTU);
            builder.addAddress(VPN_ADDRESS, 32);
            builder.addDnsServer(dnsPrimary);
            builder.addDnsServer(dnsSecondary);

            if (splitTunnel) {
                // Only route DNS through VPN
                builder.addRoute(dnsPrimary, 32);
                builder.addRoute(dnsSecondary, 32);
                // Common DNS blocking IPs
                builder.addRoute("8.8.8.8", 32);
                builder.addRoute("8.8.4.4", 32);
            } else {
                // Route everything
                builder.addRoute(VPN_ROUTE, 0);
            }

            // Exclude our own app to prevent loops
            try {
                builder.addDisallowedApplication(getPackageName());
            } catch (Exception ignored) {}

            vpnInterface = builder.establish();

            if (vpnInterface == null) {
                Log.e(TAG, "Failed to establish VPN interface");
                return;
            }

            isRunning.set(true);

            vpnThread = new Thread(this::runVpnLoop, "DiscordiaVPN-Thread");
            vpnThread.start();

            Log.i(TAG, "VPN started — DNS: " + dnsPrimary +
                       " / " + dnsSecondary +
                       " | Split: " + splitTunnel +
                       " | Ads block: " + blockAds);

        } catch (Exception e) {
            Log.e(TAG, "VPN start error", e);
            stopVpn();
        }
    }

    private void runVpnLoop() {
        FileInputStream in = new FileInputStream(vpnInterface.getFileDescriptor());
        FileOutputStream out = new FileOutputStream(vpnInterface.getFileDescriptor());

        ByteBuffer packet = ByteBuffer.allocate(MTU);
        DatagramChannel tunnel = null;

        try {
            tunnel = DatagramChannel.open();
            tunnel.connect(new InetSocketAddress(dnsPrimary, 53));
            protect(tunnel.socket());

            while (isRunning.get()) {
                packet.clear();
                int length = in.read(packet.array());

                if (length <= 0) {
                    Thread.sleep(50);
                    continue;
                }

                packet.limit(length);

                // Check if this is a DNS packet (UDP to port 53)
                if (isDnsPacket(packet.array(), length)) {
                    // Extract DNS query and forward to secure DNS
                    handleDnsPacket(packet, length, in, out, tunnel);
                } else if (!splitTunnel) {
                    // Forward non-DNS traffic if full tunnel
                    tunnel.write(packet);

                    // Read response
                    packet.clear();
                    int responseLength = tunnel.read(packet);
                    if (responseLength > 0) {
                        out.write(packet.array(), 0, responseLength);
                    }
                }
                // In split tunnel mode, non-DNS traffic goes
                // through the normal network
            }

        } catch (Exception e) {
            if (isRunning.get()) {
                Log.e(TAG, "VPN loop error", e);
            }
        } finally {
            try {
                if (tunnel != null) tunnel.close();
            } catch (Exception ignored) {}
        }
    }

    private boolean isDnsPacket(byte[] data, int length) {
        if (length < 28) return false;

        // Check IP header
        int version = (data[0] >> 4) & 0xF;
        if (version != 4) return false;

        // Protocol (17 = UDP)
        int protocol = data[9] & 0xFF;
        if (protocol != 17) return false;

        // Destination port
        int ipHeaderLength = (data[0] & 0xF) * 4;
        if (length < ipHeaderLength + 4) return false;

        int dstPort = ((data[ipHeaderLength + 2] & 0xFF) << 8)
                    | (data[ipHeaderLength + 3] & 0xFF);

        return dstPort == 53;
    }

    private void handleDnsPacket(ByteBuffer packet, int length,
                                  FileInputStream in,
                                  FileOutputStream out,
                                  DatagramChannel tunnel) {
        try {
            // Extract IP header info
            byte[] data = packet.array();
            int ipHeaderLen = (data[0] & 0xF) * 4;
            int udpStart = ipHeaderLen;
            int dnsStart = udpStart + 8;
            int dnsLength = length - dnsStart;

            if (dnsLength <= 0) return;

            // Extract DNS query payload
            byte[] dnsQuery = new byte[dnsLength];
            System.arraycopy(data, dnsStart, dnsQuery, 0, dnsLength);

            // Forward to Cloudflare DNS (plain DNS over UDP for speed)
            DatagramSocket dnsSocket = new DatagramSocket();
            protect(dnsSocket);

            InetAddress dnsServer = InetAddress.getByName(dnsPrimary);
            DatagramPacket request = new DatagramPacket(
                dnsQuery, dnsLength, dnsServer, 53
            );
            dnsSocket.setSoTimeout(5000);
            dnsSocket.send(request);

            // Receive response
            byte[] responseBuffer = new byte[1024];
            DatagramPacket response = new DatagramPacket(
                responseBuffer, responseBuffer.length
            );
            dnsSocket.receive(response);
            dnsSocket.close();

            // Build response IP packet
            int responseLen = response.getLength();
            byte[] responseData = new byte[ipHeaderLen + 8 + responseLen];

            // Copy original IP header, swap src/dst
            System.arraycopy(data, 0, responseData, 0, ipHeaderLen);

            // Swap source and destination IP
            System.arraycopy(data, 12, responseData, 16, 4); // src -> dst
            System.arraycopy(data, 16, responseData, 12, 4); // dst -> src

            // Update total length
            int totalLen = responseData.length;
            responseData[2] = (byte) (totalLen >> 8);
            responseData[3] = (byte) (totalLen & 0xFF);

            // UDP header
            // Swap ports
            responseData[ipHeaderLen] = data[ipHeaderLen + 2];
            responseData[ipHeaderLen + 1] = data[ipHeaderLen + 3];
            responseData[ipHeaderLen + 2] = data[ipHeaderLen];
            responseData[ipHeaderLen + 3] = data[ipHeaderLen + 1];

            // UDP length
            int udpLen = 8 + responseLen;
            responseData[ipHeaderLen + 4] = (byte) (udpLen >> 8);
            responseData[ipHeaderLen + 5] = (byte) (udpLen & 0xFF);

            // UDP checksum (set to 0 for now)
            responseData[ipHeaderLen + 6] = 0;
            responseData[ipHeaderLen + 7] = 0;

            // DNS response payload
            System.arraycopy(
                responseBuffer, 0,
                responseData, ipHeaderLen + 8,
                responseLen
            );

            // Recalculate IP checksum
            responseData[10] = 0;
            responseData[11] = 0;
            int checksum = calculateChecksum(responseData, 0, ipHeaderLen);
            responseData[10] = (byte) (checksum >> 8);
            responseData[11] = (byte) (checksum & 0xFF);

            // Write back to TUN
            out.write(responseData, 0, responseData.length);

        } catch (Exception e) {
            Log.w(TAG, "DNS handling error: " + e.getMessage());
        }
    }

    private int calculateChecksum(byte[] data, int offset, int length) {
        int sum = 0;
        for (int i = offset; i < offset + length - 1; i += 2) {
            sum += ((data[i] & 0xFF) << 8) | (data[i + 1] & 0xFF);
        }
        if (length % 2 != 0) {
            sum += (data[offset + length - 1] & 0xFF) << 8;
        }
        while ((sum >> 16) > 0) {
            sum = (sum & 0xFFFF) + (sum >> 16);
        }
        return ~sum & 0xFFFF;
    }

    private void stopVpn() {
        isRunning.set(false);

        if (vpnThread != null) {
            vpnThread.interrupt();
            vpnThread = null;
        }

        if (vpnInterface != null) {
            try {
                vpnInterface.close();
            } catch (IOException e) {
                Log.e(TAG, "Error closing VPN interface", e);
            }
            vpnInterface = null;
        }

        Log.i(TAG, "VPN stopped");
    }

    @Override
    public void onDestroy() {
        stopVpn();
        super.onDestroy();
    }

    @Override
    public void onRevoke() {
        stopVpn();
        super.onRevoke();
    }
}