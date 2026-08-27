#ifndef CHECK_TRAITS_H
#define CHECK_TRAITS_H

#include <type_traits>
#include <utility>

// ============================================================
// Generic, type-agnostic validity-check machinery.
//
// This header knows NOTHING about any specific business type
// (TradeData, ActionSignal, ActionType, ...). It only defines HOW
// a type can declare itself checkable. A new custom type becomes
// checkable in one of three ways, WITHOUT ever touching this file
// or ParameterCheck.h:
//
//   1) Give the type a public "bool isValid() const" member.
//        -> default_check() will call it automatically.
//        e.g. struct IntRange { ... bool isValid() const {...} };
//
//   2) If the type is container-like (has "empty()"),
//        -> default_check() treats "not empty" as valid.
//        e.g. std::vector<double>, std::deque<double>, ...
//        This covers DoubleVector / TradeDataVector automatically -
//        no extra code needed anywhere.
//
//   3) If the type can't have member functions (e.g. an enum),
//      or you don't want/can't modify its definition, specialize
//      check_traits<T> for it. Put the specialization right next
//      to the type's own definition (e.g. in Types.h), NOT in
//      ParameterCheck.h.
// ============================================================

// --- detect "bool isValid() const" ---------------------------------
template <typename, typename = void>
struct has_isValid_method : std::false_type {};

template <typename T>
struct has_isValid_method<T, std::void_t<decltype(std::declval<const T&>().isValid())>>
    : std::true_type {};

template <typename T>
inline constexpr bool has_isValid_v = has_isValid_method<T>::value;

// --- detect "empty()" (container-like types) ------------------------
template <typename, typename = void>
struct has_empty_method : std::false_type {};

template <typename T>
struct has_empty_method<T, std::void_t<decltype(std::declval<const T&>().empty())>>
    : std::true_type {};

template <typename T>
inline constexpr bool has_empty_v = has_empty_method<T>::value;

// --- fallback / explicit customization point -------------------------
// Specialize this for a type when isValid()/empty() aren't a fit
// (typically enums), or when you want to override the automatic
// behavior for some type. Example (in Types.h, next to ActionType):
//
//   template<>
//   struct check_traits<ActionType>
//   {
//       static bool check(ActionType v)
//       {
//           return v == ActionType::BUY || v == ActionType::SELL || v == ActionType::HOLD;
//       }
//   };
template <typename T, typename Enable = void>
struct check_traits
{
    static bool check(const T&)
    {
        static_assert(sizeof(T) == 0,
            "default_check: No check available for this type.\n"
            "Fix by one of:\n"
            "  1) Add 'bool isValid() const' to the type, or\n"
            "  2) Make sure it has 'empty()' if it's container-like, or\n"
            "  3) Specialize check_traits<T> for this type (near the type's definition).");
        return false;
    }
};

#endif // CHECK_TRAITS_H
