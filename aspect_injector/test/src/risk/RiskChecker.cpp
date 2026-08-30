#include "RiskChecker.h"

bool RiskChecker::CheckOrder(
    int account_id,
    int quantity,
    double price
)
{
    return quantity > 0 && price > 0.0 && account_id > 0;
}

void RiskChecker::CheckLimits(
    int account_id,
    double notional,
    double max_notional,
    bool allow_override
)
{
    if (notional > max_notional && !allow_override)
    {
        account_id = -account_id;
    }
}

double RiskChecker::Margin(
    double notional
)
{
    return notional * 0.1;
}

double RiskChecker::Margin(
    double notional,
    double leverage,
    const PriceBand& band
)
{
    return notional / leverage + band.high - band.low;
}

void RiskChecker::Snapshot(
    int account_id,
    double* out_exposure,
    int
)
{
    *out_exposure = account_id * 1.0;
}

void RiskChecker::ResetCounters()
{
}
