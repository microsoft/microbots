// app.c — A simple greeting program with a syntax error
#include <stdio.h>

int add(int a, int b) {
    return a + b
}

int main(void) {
    printf("Hello, Microbots!\n");
    printf("2 + 3 = %d\n", add(2, 3));
    return 0;
}
