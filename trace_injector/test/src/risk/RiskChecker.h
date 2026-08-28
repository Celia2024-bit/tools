#pragma once

//
// The multi-parameter fixture. Everything else under test/src takes zero or one
// parameter, which is not enough to tell a working validate injection from one
// that happens to emit the right number of lines.
//
// Deliberately built from built-in types and a local struct only. Pulling in
// <string> or <vector> would make clang emit a fatal "file not found" on every
// parse (no sysroot is configured), and the base_class scenarios assert on the
// absence of exactly that warning.
//
struct PriceBand
{
    double low;
    double high;
};


class RiskChecker
{
public:

    //
    // Three and four parameters: the ordinary case.
    //
    bool CheckOrder(
        int account_id,
        int quantity,
        double price
    );

    void CheckLimits(
        int account_id,
        double notional,
        double max_notional,
        bool allow_override
    );

    //
    // Overloaded, with different arities. Both definitions share one qualified
    // name, so the parameter list has to come from the node being injected into
    // rather than from a name lookup.
    //
    double Margin(
        double notional
    );

    double Margin(
        double notional,
        double leverage,
        const PriceBand& band
    );

    //
    // A pointer out-parameter, and a third parameter with no name at all.
    // clang reports the unnamed one as a PARM_DECL with an empty spelling —
    // there is nothing to put in the name table, so it is skipped.
    //
    void Snapshot(
        int account_id,
        double* out_exposure,
        int
    );

    //
    // No parameters, so no validate block even when the rule asks for one.
    //
    void ResetCounters();
};
