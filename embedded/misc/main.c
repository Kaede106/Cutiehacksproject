#include <stdint.h>

#define RCC_AHB2ENR  (*(volatile uint32_t *)0x4002104C)
#define RCC_APB1ENR1 (*(volatile uint32_t *)0x40021058)

#define GPIOA_MODER  (*(volatile uint32_t *)0x48000000)
#define GPIOA_AFRL   (*(volatile uint32_t *)0x48000020)

#define USART2_BASE  0x40004400

#define USART_CR1    (*(volatile uint32_t *)(USART2_BASE + 0x00))
#define USART_BRR    (*(volatile uint32_t *)(USART2_BASE + 0x0C))
#define USART_ISR    (*(volatile uint32_t *)(USART2_BASE + 0x1C))
#define USART_RDR    (*(volatile uint32_t *)(USART2_BASE + 0x24))
#define USART_TDR    (*(volatile uint32_t *)(USART2_BASE + 0x28))

void uart_init(void)
{
    // Enable GPIOA and USART2 clocks
    RCC_AHB2ENR |= (1U << 0);
    RCC_APB1ENR1 |= (1U << 17);

    // PA2 and PA3 alternate function mode
    GPIOA_MODER &= ~((3U << 4) | (3U << 6));
    GPIOA_MODER |= (2U << 4) | (2U << 6);

    // Alternate function 7 = USART2
    GPIOA_AFRL &= ~((15U << 8) | (15U << 12));
    GPIOA_AFRL |= (7U << 8) | (7U << 12);

    // 115200 baud, assuming 4 MHz USART clock
    USART_CR1 = 0;
    USART_BRR = 4000000 / 115200;

    // Enable USART, transmitter and receiver
    USART_CR1 = (1U << 0) | (1U << 2) | (1U << 3);
}

void uart_putc(char c)
{
    while (!(USART_ISR & (1U << 7)));

    USART_TDR = c;
}

char uart_getc(void)
{
    while (!(USART_ISR & (1U << 5)));

    return (char)USART_RDR;
}

void uart_print(const char *str)
{
    while (*str)
        uart_putc(*str++);
}

void uart_print_num(int n)
{
    char buffer[12];
    int i = 0;

    if (n < 0) {
        uart_putc('-');
        n = -n;
    }

    if (n == 0) {
        uart_putc('0');
        return;
    }

    while (n > 0) {
        buffer[i++] = '0' + n % 10;
        n /= 10;
    }

    while (i > 0)
        uart_putc(buffer[--i]);
}



int main(void)
{
    uart_init();

    while (1) {
        uart_print("\r\nEnter a number (1-9): ");

        char input = uart_getc();

        uart_putc(input);
        uart_print("\r\n");

        if (input < '1' || input > '9') {
            uart_print("Invalid input!\r\n");
            continue;
        }

        int n = input - '0';

        for (int i = 0; i < n; i++) {
            uart_print("Iteration: ");
            uart_print_num(i);
            uart_print("\r\n");
        }

        uart_print("Done!\r\n");
    }
}
