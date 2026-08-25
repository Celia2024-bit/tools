#pragma once

class UnrelatedClass
{
public:

    void Print();

    int GetValue() const;
    void OnError(int err_code) override;

};