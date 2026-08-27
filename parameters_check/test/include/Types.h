#ifndef TYPES_H
#define TYPES_H

#include <chrono>              // For std::chrono (e.g., sleep_for, seconds)
#include <cmath>               // For std::isfinite
#include <string>
#include <vector>
#include <deque>
#include "CheckTraits.h"       // check_traits<T> / has_isValid_v / has_empty_v customization points

enum class ActionType
{
    BUY,
    SELL,
    HOLD,
};


// ActionType is an enum, so it can't have an isValid() member.
// Make it checkable via a check_traits<T> specialization instead -
// ParameterCheck.h never needs to know about ActionType at all.
template <>
struct check_traits<ActionType>
{
    static bool check(ActionType value)
    {
        return value == ActionType::BUY ||
               value == ActionType::SELL ||
               value == ActionType::HOLD;
    }
};

struct TradeData
{
    double price_;
    long long timestamp_ms_;
    std::string symbol_;

    TradeData(double price) : price_(price)
    {
        timestamp_ms_ = std::chrono::duration_cast<std::chrono::milliseconds>(
                                    std::chrono::system_clock::now().time_since_epoch())
                                    .count();
    }
    TradeData() : price_(0.0), timestamp_ms_(0) {}

    // Self-contained validity check. default_check() picks this up
    // automatically (see CheckTraits.h) - no edits needed in ParameterCheck.h.
    bool isValid() const {
        return price_ > 0.0 && timestamp_ms_ > 0;
    }
};

struct ActionSignal
{
    ActionType type_;
    double price_;
    double amount_;
    long long timestamp_ms_;

    ActionSignal(ActionType type, double price, double amount)
        : type_(type), price_(price), amount_(amount)
    {
        timestamp_ms_ = std::chrono::duration_cast<std::chrono::milliseconds>(
                                    std::chrono::system_clock::now().time_since_epoch())
                                    .count();
    }
    ActionSignal() : type_(ActionType::HOLD), price_(0.0), amount_(0.0), timestamp_ms_(0) {}

    // Self-contained validity check (mirrors the old default_check<ActionSignal>
    // logic), but now lives with the type instead of in ParameterCheck.h.
    bool isValid() const {
        const bool typeOk = check_traits<ActionType>::check(type_);
        const bool priceOk = std::isfinite(price_) && price_ > 0.0;
        const bool amountOk = std::isfinite(amount_) && amount_ > 0.0;
        return typeOk && priceOk && amountOk && timestamp_ms_ > 0;
    }
};

struct IntRange {
public:
    int x;
    int min;
    int max;

    IntRange(int value = 0, int minimum = 0, int maximum = 0)
        : x(value), min(minimum), max(maximum) {}

    bool isValid() const {
        return x >= min && x <= max;
    }
};

#endif // TYPES_H
