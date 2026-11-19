package com.mazawallet;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.math.BigDecimal;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;

/** Pure Java conversion from indexer JSON to display rows. */
public final class ExplorerParse {
    private ExplorerParse() {}

    public static final class Result {
        public final String heading;
        public final List<String> rows;
        public final boolean error;
        /** Tx view: the confirming height (null = unconfirmed) + txid, and
         *  the row index carrying the proof status line (IDX-8). */
        public final Long txHeight;
        public final String txTxid;
        public final int proofRowIndex;
        /** Address view: verifiable history rows (IDX-8 tap-to-verify). */
        public final List<HistoryEntry> history;

        Result(String heading, List<String> rows, boolean error) {
            this(heading, rows, error, null, null, -1, null);
        }

        Result(String heading, List<String> rows, boolean error, Long txHeight,
                String txTxid, int proofRowIndex, List<HistoryEntry> history) {
            this.heading = heading;
            this.rows = rows;
            this.error = error;
            this.txHeight = txHeight;
            this.txTxid = txTxid;
            this.proofRowIndex = proofRowIndex;
            this.history = history == null
                    ? new ArrayList<HistoryEntry>() : history;
        }
    }

    /** One address-history row the user can tap to verify on-chain. */
    public static final class HistoryEntry {
        public final String txid;
        public final long height;
        public final int rowIndex;
        private boolean done;

        HistoryEntry(String txid, long height, int rowIndex) {
            this.txid = txid;
            this.height = height;
            this.rowIndex = rowIndex;
        }

        /** Claims this row's single verification attempt: true exactly once,
         *  so a repeated tap can never re-fetch the same proof. */
        boolean markTapStarted() {
            if (done) return false;
            done = true;
            return true;
        }
    }

    /** Parsed /api/v0/proof response, ready for MerkleVerify.verify. */
    public static final class Proof {
        public final String txid;
        public final String merkleroot;
        public final String[] merkle;
        public final int pos;
        /** Null on success; the indexer error text otherwise. */
        public final String error;

        Proof(String txid, String merkleroot, String[] merkle, int pos,
                String error) {
            this.txid = txid;
            this.merkleroot = merkleroot;
            this.merkle = merkle;
            this.pos = pos;
            this.error = error;
        }
    }

    public static Result address(String text) { return parse("Address", text, 0); }
    public static Result transaction(String text) { return parse("Transaction", text, 1); }
    public static Result block(String text) { return parse("Block", text, 2); }

    public static Result error(String message) {
        ArrayList<String> rows = new ArrayList<String>();
        rows.add(message == null || message.trim().length() == 0
                ? "Could not read the indexer response." : message.trim());
        return new Result("Explorer error", rows, true);
    }

    private static Result parse(String heading, String text, int kind) {
        try {
            JSONObject o = new JSONObject(text);
            if (o.has("error")) return error(o.optString("error", "Indexer error."));
            if (kind == 0) return parseAddress(o);
            if (kind == 1) return parseTransaction(o);
            return parseBlock(o);
        } catch (JSONException | RuntimeException e) {
            return error("The indexer returned an unreadable " + heading.toLowerCase(Locale.US)
                    + " response.");
        }
    }

    private static Result parseAddress(JSONObject o) throws JSONException {
        ArrayList<String> rows = new ArrayList<String>();
        rows.add(o.getString("address"));
        rows.add("Balance: " + coins(o.getLong("balance_sats")));
        rows.add("Transactions: " + o.getLong("tx_count"));
        ArrayList<HistoryEntry> history = new ArrayList<HistoryEntry>();
        JSONArray txs = o.getJSONArray("txs");
        for (int i = 0; i < txs.length(); i++) {
            JSONObject tx = txs.getJSONObject(i);
            String arrow = "in".equals(tx.optString("direction")) ? "<-" : "->";
            String txid = tx.getString("txid");
            long height = tx.getLong("height");
            history.add(new HistoryEntry(txid, height, rows.size()));
            rows.add(txid + "\nBlock " + height + "  "
                    + absolute(tx.getLong("time")) + "  " + arrow + " "
                    + tx.getLong("value_sats") + " sats");
        }
        if (o.optBoolean("truncated", false)) rows.add("History truncated to newest entries.");
        return new Result("Address", rows, false, null, null, -1, history);
    }

    private static Result parseTransaction(JSONObject o) throws JSONException {
        ArrayList<String> rows = new ArrayList<String>();
        rows.add("Txid: " + o.getString("txid"));
        rows.add("Confirmations: " + o.getLong("confirmations"));
        Long height = o.isNull("height") ? null : Long.valueOf(o.getLong("height"));
        if (height == null) rows.add("Unconfirmed");
        else rows.add("In block " + o.getLong("height"));
        rows.add("Block hash: " + nullable(o, "blockhash"));
        rows.add("Size: " + o.getLong("size") + " bytes");
        JSONArray vin = o.getJSONArray("vin");
        rows.add("Inputs: " + vin.length());
        for (int i = 0; i < vin.length(); i++) {
            JSONObject in = vin.getJSONObject(i);
            rows.add("Input " + (i + 1) + ": " + addresses(in.optJSONArray("addresses"))
                    + "  " + sats(in, "value_sats")
                    + (in.optBoolean("coinbase", false) ? "  coinbase" : ""));
        }
        JSONArray vout = o.getJSONArray("vout");
        rows.add("Outputs: " + vout.length());
        for (int i = 0; i < vout.length(); i++) {
            JSONObject out = vout.getJSONObject(i);
            rows.add("Output " + out.getLong("n") + ": "
                    + addresses(out.optJSONArray("addresses")) + "  "
                    + out.getLong("value_sats") + " sats  "
                    + out.optString("script_type", "other"));
        }
        // IDX-8: the activity replaces this line with the live proof-check
        // result; an unconfirmed tx has no proof to check.
        int proofRow = rows.size();
        rows.add(height == null ? "Proof: not available (unconfirmed)"
                : "Proof: checking...");
        return new Result("Transaction", rows, false, height,
                o.getString("txid"), proofRow, null);
    }

    private static Result parseBlock(JSONObject o) throws JSONException {
        ArrayList<String> rows = new ArrayList<String>();
        rows.add("Height: " + o.getLong("height"));
        rows.add("Hash: " + o.getString("hash"));
        rows.add("Merkle root: " + o.getString("merkleroot"));
        rows.add("Transactions: " + o.getLong("ntx"));
        rows.add("Time: " + absolute(o.getLong("time")));
        rows.add("Difficulty: " + o.getDouble("difficulty"));
        JSONArray txids = o.getJSONArray("txids");
        int shown = Math.min(50, txids.length());
        for (int i = 0; i < shown; i++) rows.add((i + 1) + ". " + txids.getString(i));
        if (txids.length() > shown || o.optBoolean("txids_truncated", false)) {
            rows.add("Transaction list truncated.");
        }
        return new Result("Block", rows, false);
    }

    /** IDX-8: parse a /api/v0/proof response for MerkleVerify.verify. */
    public static Proof proof(String text) {
        try {
            JSONObject o = new JSONObject(text);
            if (o.has("error")) {
                return new Proof(null, null, null, -1,
                        o.optString("error", "Indexer error."));
            }
            JSONArray merkleArr = o.getJSONArray("merkle");
            String[] merkle = new String[merkleArr.length()];
            for (int i = 0; i < merkleArr.length(); i++) {
                merkle[i] = merkleArr.getString(i);
            }
            return new Proof(o.getString("txid"), o.getString("merkleroot"),
                    merkle, o.getInt("pos"), null);
        } catch (JSONException | RuntimeException e) {
            return new Proof(null, null, null, -1,
                    "The indexer returned an unreadable proof response.");
        }
    }

    private static String coins(long sats) {
        return BigDecimal.valueOf(sats).movePointLeft(8).toPlainString() + " MAZA";
    }

    private static String absolute(long seconds) {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US);
        f.setTimeZone(TimeZone.getDefault());
        return f.format(new Date(seconds * 1000L));
    }

    private static String nullable(JSONObject o, String key) {
        return o.isNull(key) ? "not available" : o.optString(key, "not available");
    }

    private static String sats(JSONObject o, String key) {
        return o.isNull(key) ? "value not available" : o.optLong(key) + " sats";
    }

    private static String addresses(JSONArray values) {
        if (values == null || values.length() == 0) return "address not available";
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < values.length(); i++) {
            if (i != 0) out.append(", ");
            out.append(values.optString(i));
        }
        return out.toString();
    }
}
