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

        Result(String heading, List<String> rows, boolean error) {
            this.heading = heading;
            this.rows = rows;
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
        JSONArray txs = o.getJSONArray("txs");
        for (int i = 0; i < txs.length(); i++) {
            JSONObject tx = txs.getJSONObject(i);
            String arrow = "in".equals(tx.optString("direction")) ? "<-" : "->";
            rows.add(tx.getString("txid") + "\nBlock " + tx.getLong("height") + "  "
                    + absolute(tx.getLong("time")) + "  " + arrow + " "
                    + tx.getLong("value_sats") + " sats");
        }
        if (o.optBoolean("truncated", false)) rows.add("History truncated to newest entries.");
        return new Result("Address", rows, false);
    }

    private static Result parseTransaction(JSONObject o) throws JSONException {
        ArrayList<String> rows = new ArrayList<String>();
        rows.add("Txid: " + o.getString("txid"));
        rows.add("Confirmations: " + o.getLong("confirmations"));
        if (o.isNull("height")) rows.add("Unconfirmed");
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
        rows.add("Proof: not available");
        return new Result("Transaction", rows, false);
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
        rows.add("Proof: not available");
        return new Result("Block", rows, false);
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
