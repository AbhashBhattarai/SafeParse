# Makefile for SafeParse C Correctness Test Harness
#
# Targets:
#   all       - Default target; builds run_cases
#   run_cases - Compiles run_cases.c with strict C11 flags and sanitizers
#   clean     - Removes compiled binaries and intermediate build artifacts

CC ?= gcc
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -I generated

.PHONY: all clean

all: run_cases

run_cases: run_cases.c generated/udp_naive.h generated/udp_optimized.h generated/png_ihdr_naive.h generated/png_ihdr_optimized.h generated/dns_naive.h generated/dns_optimized.h
	$(CC) $(CFLAGS) run_cases.c -o run_cases

clean:
	rm -f run_cases run_cases.exe *.o
