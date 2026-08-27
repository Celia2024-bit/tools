#include <iostream>
#include <cassert>
#include <vector>
#include <string>
#include <limits>
#include "output/ParameterCheck.h"
#include "include/Types.h"

// Helper function to print test header and result status
void print_test_result(const char* test_name, bool result, bool expected)
{
    std::cout << "  [" << (result == expected ? "PASS" : "FAIL") << "] " 
              << test_name << " (Returned: " << (result ? "true" : "false") << ")\n";
}

// Simulated business functions
bool executeOrder(double price, int quantity, ActionType type, const std::string& symbol)
{
    const char* names[] = { "price", "quantity", "type", "symbol" };
    return validate_params("executeOrder", names, price, quantity, type, symbol);
}

bool processDataSimple(double val, IntRange range)
{
    return validate_params("processDataSimple", val, range);
}

// -------------------------------------------------------------
// Test Case 1: Basic Types
// -------------------------------------------------------------
void test_basic_types()
{
    std::cout << "\n=== [Test 1] Basic Types Check ===\n";
    
    int valid_int = 10;
    int invalid_int = -5;
    double valid_double = 3.14;
    double invalid_double_nan = std::numeric_limits<double>::quiet_NaN();
    int* ptr_valid = &valid_int;
    int* ptr_null = nullptr;

    bool res1 = validate_params("test_basic_types_pass", valid_int, valid_double, ptr_valid);
    print_test_result("All parameters valid", res1, true);
    assert(res1 == true);

    std::cout << "-> Expecting error logs for invalid parameters below:\n";
    bool res2 = validate_params("test_basic_types_fail", invalid_int, invalid_double_nan, ptr_null);
    print_test_result("Invalid parameters detected", res2, false);
    assert(res2 == false);
}

// -------------------------------------------------------------
// Test Case 2: Custom Types & Enums
// -------------------------------------------------------------
void test_custom_types()
{
    std::cout << "\n=== [Test 2] Custom Types & Enums Check ===\n";

    TradeData valid_trade(150.5);
    TradeData invalid_trade(-10.0);

    ActionSignal valid_signal(ActionType::BUY, 100.0, 50.0);
    ActionSignal invalid_signal(ActionType::SELL, -5.0, 50.0);

    IntRange valid_range(5, 1, 10);
    IntRange invalid_range(15, 1, 10);

    ActionType valid_enum = ActionType::SELL;

    const char* names[] = { "trade", "signal", "range", "action" };
    
    bool res1 = validate_params("test_custom_types_pass", names, valid_trade, valid_signal, valid_range, valid_enum);
    print_test_result("Valid custom types check", res1, true);
    assert(res1 == true);

    std::cout << "-> Expecting error logs for invalid custom types below:\n";
    bool res2 = validate_params("test_custom_types_fail", names, invalid_trade, invalid_signal, invalid_range, valid_enum);
    print_test_result("Invalid custom types detected", res2, false);
    assert(res2 == false);
}

// -------------------------------------------------------------
// Test Case 3: Container Types
// -------------------------------------------------------------
void test_container_types()
{
    std::cout << "\n=== [Test 3] Container Types Check ===\n";

    std::vector<double> valid_vec = { 1.1, 2.2, 3.3 };
    std::vector<double> empty_vec;
    std::string valid_str = "Hello";
    std::string empty_str = "";

    bool res1 = validate_params("test_container_pass", valid_vec, valid_str);
    print_test_result("Non-empty containers check", res1, true);
    assert(res1 == true);

    std::cout << "-> Expecting error logs for empty containers below:\n";
    bool res2 = validate_params("test_container_fail", empty_vec, empty_str);
    print_test_result("Empty containers detected", res2, false);
    assert(res2 == false);
}

// -------------------------------------------------------------
// Test Case 4: Business Simulation
// -------------------------------------------------------------
void test_business_simulation()
{
    std::cout << "\n=== [Test 4] Business Function Simulation ===\n";

    bool pass = executeOrder(99.9, 10, ActionType::BUY, "AAPL");
    print_test_result("executeOrder with valid args", pass, true);
    assert(pass == true);

    std::cout << "-> Expecting error logs for executeOrder invalid args below:\n";
    bool fail = executeOrder(-1.0, 0, ActionType::BUY, "");
    print_test_result("executeOrder rejected invalid args", fail, false);
    assert(fail == false);

    std::cout << "-> Expecting error log for processDataSimple out of range below:\n";
    IntRange r(20, 1, 10);
    bool fail_simple = processDataSimple(5.5, r);
    print_test_result("processDataSimple rejected invalid range", fail_simple, false);
    assert(fail_simple == false);
}

int main()
{
    std::cout << "========================================\n";
    std::cout << "      Starting validate_params Tests          \n";
    std::cout << "========================================\n";

    test_basic_types();
    test_custom_types();
    test_container_types();
    test_business_simulation();

    std::cout << "\n========================================\n";
    std::cout << "  ALL TESTS COMPLETED SUCCESSFULLY!    \n";
    std::cout << "========================================\n";

    return 0;
}