package ioniq6.cpclimate;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * The phone's two side streams for video playback, "settings" (BB493F61-…) and "overlay" (E3DC3EA6-…).
 * The phone opens both for every video; what it sends there isn't known (LIVI only records them, as
 * "video settings" and "video overlay"). The overlay stream is the one place CarPlay could hand the car its
 * own player controls or titles, so this records it.
 *
 * The native SETUP handler gives them ports 7138 and 7139 with their keys in files/cpc-vs-4.key and
 * cpc-vs-5.key. This decrypts them like the iAP stream (IapChannel), answers each sync package with an empty
 * reply, and records every package: its decoded form (OPACK, or a bplist, or OPACK holding a bplist as LIVI's
 * describe_setting reads them) in files/cpc-video-side/&lt;session&gt;/&lt;name&gt;.txt, and its raw body as a
 * numbered .bin beside it. Nothing is acted on. A session is one start of CarPlay's process, numbered (0001-, 0002-,
 * then its start time as a label: the clock can still read 2015 that early after boot), so a restart doesn't
 * overwrite what was recorded; the newest KEEP_SESSIONS are kept. The mod's service
 * (svc/video-usb.sh) copies them to a USB stick that has a CarPlayUltraLite-Video folder.
 */
final class VideoSideChannel extends Thread {
    static final String DIR = "cpc-video-side";
    static final int MAX_FILES = 400;          // per stream and process start
    static final long MAX_TEXT = 2L * 1024 * 1024;
    static final int MAX_DESCRIBED = 4000;     // characters of a decoded package in the text file
    static final int MAX_LOGGED = 40;          // packages per stream in the HMG-API log
    static final int KEEP_SESSIONS = 5;
    /** this process's folder name, made on first use (session()) */
    static String session;

    final File dir, out;
    final VsChannel.Log log;
    final String name;
    final int port;
    final String keys;
    int saved;

    VideoSideChannel(File dir, VsChannel.Log log, String name, int port, String keys) {
        super("cp-climate-video-" + name);
        this.dir = dir;
        this.out = new File(dir, DIR);
        this.log = log;
        this.name = name;
        this.port = port;
        this.keys = keys;
        setDaemon(true);
    }

    @Override
    public void run() {
        try {
            ServerSocket s = new ServerSocket();
            s.setReuseAddress(true);
            s.bind(new InetSocketAddress(port));
            log.log("video " + name + " stream: listening on port " + port + " (recorded in files/" + DIR + ")");
            while (true) {
                final Socket sock = s.accept();
                new Thread("cp-climate-video-" + name + "-conn") {
                    @Override
                    public void run() {
                        serve(sock);
                    }
                }.start();
            }
        } catch (Throwable t) {
            log.log("video " + name + " stream: listener stopped: " + t);
        }
    }

    void serve(Socket sock) {
        log.log("video " + name + " stream: connection from " + sock.getRemoteSocketAddress());
        int packages = 0;
        long total = 0;
        try {
            byte[] k = IapChannel.readKeys(dir, keys);
            if (k == null) {
                log.log("video " + name + " stream: no keys from the SETUP, closed");
                return;
            }
            byte[] rd = new byte[32], wr = new byte[32];
            System.arraycopy(k, 8, rd, 0, 32);
            System.arraycopy(k, 40, wr, 0, 32);
            ChaChaPoly cipher = new ChaChaPoly(rd, wr);
            InputStream in = sock.getInputStream();
            VsChannel.Writer w = new VsChannel.Writer(sock, sock.getOutputStream(), cipher);
            record("---- connection from " + sock.getRemoteSocketAddress(), null, 0, 0);
            byte[] sealed = new byte[64 * 1024];
            int have = 0;
            ByteArrayOutputStream plain = new ByteArrayOutputStream();
            while (true) {
                if (have == sealed.length) sealed = java.util.Arrays.copyOf(sealed, sealed.length * 2);
                int n = in.read(sealed, have, sealed.length - have);
                if (n < 0) break;
                have += n;
                int used = cipher.open(sealed, have, plain);
                if (used < 0) {
                    log.log("video " + name + " stream: a frame didn't authenticate, closed");
                    return;
                }
                System.arraycopy(sealed, used, sealed, 0, have - used);
                have -= used;
                byte[] p = plain.toByteArray();
                int at = 0;
                while (p.length - at >= VsChannel.HEADER) {
                    int size = VsChannel.be32(p, at);
                    if (size < VsChannel.HEADER || size > VsChannel.MAX_PACKAGE) {
                        log.log("video " + name + " stream: implausible package size " + size + ", closed");
                        return;
                    }
                    if (p.length - at < size) break;
                    int kind = VsChannel.be32(p, at + 4), type = VsChannel.be32(p, at + 16);
                    long token = (long) VsChannel.be32(p, at + 20) << 32 | (VsChannel.be32(p, at + 24) & 0xffffffffL);
                    int len = size - VsChannel.HEADER;
                    total += len;
                    if (kind == VsChannel.SYNC) w.send(VsChannel.pack(VsChannel.REPLY, 0, token, new byte[0]));
                    byte[] body = java.util.Arrays.copyOfRange(p, at + VsChannel.HEADER, at + size);
                    String what = describe(body);
                    String head = VsChannel.tag(kind) + "/" + VsChannel.tag(type) + " " + len + " B";
                    record(head + ": " + what, body, kind, type);
                    if (packages++ < MAX_LOGGED) log.log("video " + name + " " + head + ": " + clip(what, 300));
                    at += size;
                }
                plain.reset();
                plain.write(p, at, p.length - at);
            }
            log.log("video " + name + " stream: closed by the phone after " + packages + " package(s), " + total + " B");
        } catch (Throwable t) {
            log.log("video " + name + " stream: ended after " + packages + " package(s): " + t);
        } finally {
            record("---- closed after " + packages + " package(s), " + total + " B", null, 0, 0);
            VsChannel.close(sock);
        }
    }

    /** what a package body holds, decoded as far as it goes */
    static String describe(byte[] b) {
        if (b.length == 0) return "(empty)";
        try {
            return "bplist " + show(Bplist.decode(b));
        } catch (Throwable ignored) {
        }
        try {
            Object v = OpackCodec.decode(b);
            // LIVI's describe_setting: OPACK {messageType, data: bplist}
            if (v instanceof Map) {
                Object data = ((Map<?, ?>) v).get("data");
                if (data instanceof byte[]) {
                    try {
                        Object inner = Bplist.decode((byte[]) data);
                        return "opack " + show(v) + " data as bplist " + show(inner);
                    } catch (Throwable ignored) {
                    }
                }
            }
            return "opack " + show(v);
        } catch (Throwable ignored) {
        }
        return "raw " + IapChannel.hex(b, 0, Math.min(b.length, 64)) + (b.length > 64 ? "…" : "");
    }

    /** a decoded value as text: maps, lists, strings, numbers, data as hex (its first 48 bytes) */
    static String show(Object v) {
        StringBuilder s = new StringBuilder();
        show(v, s, 0);
        return s.toString();
    }

    static void show(Object v, StringBuilder s, int depth) {
        if (s.length() > MAX_DESCRIBED || depth > 12) {
            s.append('…');
            return;
        }
        if (v instanceof Map) {
            s.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> e : ((Map<?, ?>) v).entrySet()) {
                if (!first) s.append(", ");
                first = false;
                show(e.getKey(), s, depth + 1);
                s.append(": ");
                show(e.getValue(), s, depth + 1);
            }
            s.append('}');
        } else if (v instanceof java.util.List) {
            s.append('[');
            boolean first = true;
            for (Object x : (java.util.List<?>) v) {
                if (!first) s.append(", ");
                first = false;
                show(x, s, depth + 1);
            }
            s.append(']');
        } else if (v instanceof byte[]) {
            byte[] b = (byte[]) v;
            s.append("<").append(b.length).append(" B ").append(IapChannel.hex(b, 0, Math.min(b.length, 48))).append(b.length > 48 ? "…>" : ">");
        } else if (v instanceof OpackCodec.Raw) {
            s.append("<raw ").append(((OpackCodec.Raw) v).b.length).append(" B>");
        } else if (v instanceof String) {
            s.append('"').append(v).append('"');
        } else {
            s.append(v);
        }
    }

    /**
     * This process's session folder: one more than the highest number there. Made once per process, when the old
     * ones are pruned too: the oldest go so KEEP_SESSIONS stay with this one, and 1.1.10's loose files go.
     */
    static synchronized String session(File root) {
        if (session != null) return session;
        String[] names = root.list();
        if (names == null) names = new String[0];
        java.util.Arrays.sort(names);
        int top = 0;
        List<File> folders = new java.util.ArrayList<File>();
        for (String n : names) {
            File f = new File(root, n);
            int num = number(n);
            if (f.isDirectory() && num > 0) {
                folders.add(f);
                top = Math.max(top, num);
            } else if (f.isFile()) {
                f.delete();
            }
        }
        for (int i = 0; i < folders.size() - (KEEP_SESSIONS - 1); i++) {
            File[] in = folders.get(i).listFiles();
            if (in != null) for (File x : in) x.delete();
            folders.get(i).delete();
        }
        session = String.format(Locale.US, "%04d-%s", top + 1, new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date()));
        return session;
    }

    /** a session folder's number (its first four digits), 0 if it isn't one */
    static int number(String n) {
        if (n.length() < 5 || n.charAt(4) != '-') return 0;
        try {
            return Integer.parseInt(n.substring(0, 4));
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    static String clip(String s, int n) {
        return s.length() <= n ? s : s.substring(0, n) + "…";
    }

    static final SimpleDateFormat STAMP = new SimpleDateFormat("MM-dd HH:mm:ss.SSS", Locale.US);

    /** a line in <name>.txt and, for a package, its body as <name>-NNNN-<kind>-<type>.bin (both 0600) */
    synchronized void record(String line, byte[] body, int kind, int type) {
        try {
            File here = new File(out, session(out));
            if (!here.isDirectory() && !here.mkdirs()) return;
            File text = new File(here, name + ".txt");
            if (text.length() < MAX_TEXT) {
                String stamp;
                synchronized (STAMP) {
                    stamp = STAMP.format(new Date());
                }
                FileOutputStream f = new FileOutputStream(text, true);
                try {
                    f.write((stamp + " " + clip(line, MAX_DESCRIBED) + "\n").getBytes("UTF-8"));
                } finally {
                    f.close();
                }
                text.setReadable(false, false);
                text.setReadable(true, true);
            }
            if (body != null && saved < MAX_FILES) {
                File bin = new File(here, String.format(Locale.US, "%s-%04d-%s-%s.bin", name, saved++, VsChannel.tag(kind), VsChannel.tag(type)));
                FileOutputStream f = new FileOutputStream(bin);
                try {
                    f.write(body);
                } finally {
                    f.close();
                }
                bin.setReadable(false, false);
                bin.setReadable(true, true);
            }
        } catch (Throwable ignored) {
        }
    }
}
