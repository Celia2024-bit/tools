#pragma once

namespace hot {

class AlphaEngine {
public:
    AlphaEngine() = default;
    ~AlphaEngine() = default;

    void OnTick(int symbol_id, double price, double unnamed_volume);
};

} // namespace hot