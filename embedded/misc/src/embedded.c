#include <stdint.h>
#include <../include/stm32l476xx.h>

#define ADC_DRY 2400  // Replace with your measured dry air ADC value
#define ADC_WET 1200
void delay_cycles(volatile uint32_t count)
{
    while (count--) {
        __NOP();
    }
}
void uart_init(void)
{
    // Enable GPIOA and USART2 clocks
    RCC->AHB2ENR  |= RCC_AHB2ENR_GPIOAEN;
    RCC->APB1ENR1 |= RCC_APB1ENR1_USART2EN;

    // 2. PA2 (TX) and PA3 (RX) to Alternate Function mode (10)
    GPIOA->MODER &= ~(GPIO_MODER_MODE2_Msk | GPIO_MODER_MODE3_Msk);
    GPIOA->MODER |=  (GPIO_MODER_MODE2_1 | GPIO_MODER_MODE3_1);

    // 3. Select AF7 (USART2) for PA2 and PA3
    GPIOA->AFR[0] &= ~(GPIO_AFRL_AFSEL2_Msk | GPIO_AFRL_AFSEL3_Msk);
    GPIOA->AFR[0] |=  ((7U << GPIO_AFRL_AFSEL2_Pos) | (7U << GPIO_AFRL_AFSEL3_Pos));

    // 4. Configure 9600 baud @ 4 MHz default MSI clock (4000000 / 9600 = 417)
    USART2->CR1 = 0;
    USART2->BRR = 4000000U / 9600U;

    // 5. Enable USART2, Transmitter, and Receiver
    USART2->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
}

void uart_putc(char c)
{
    while (!(USART2->ISR & USART_ISR_TXE));
    USART2->TDR = c;
}

char uart_getc(void)
{
    while (!(USART2->ISR & (1U << 5)));

    return (char)USART2->RDR;
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

void adc_init(void)
{
    // 1. Enable GPIOA and ADC clocks
    RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN | RCC_AHB2ENR_ADCEN;

    // 2. Select System Clock (4 MHz) as ADC clock source
    RCC->CCIPR &= ~RCC_CCIPR_ADCSEL_Msk;
    RCC->CCIPR |=  (3U << RCC_CCIPR_ADCSEL_Pos);

    // 3. Set PA0 to Analog Mode (11) and close analog switch (ASCR)
    GPIOA->MODER |= (GPIO_MODER_MODE0_0 | GPIO_MODER_MODE0_1);
    GPIOA->ASCR  |= GPIO_ASCR_ASC0; // Required on STM32L476xx for ADC analog input

    // 4. Exit Deep Power-Down mode and enable ADC internal voltage regulator
    ADC1->CR &= ~ADC_CR_DEEPPWD;
    ADC1->CR |=  ADC_CR_ADVREGEN;
    for (volatile int i = 0; i < 1000; i++); // Wait ~20 us for regulator startup

    // 5. Calibrate ADC (Single-Ended mode)
    ADC1->CR &= ~ADC_CR_ADCALDIF;
    ADC1->CR |=  ADC_CR_ADCAL;
    while (ADC1->CR & ADC_CR_ADCAL);

    // 6. Configure Channel 5 (PA0) as 1st conversion in regular sequence
    ADC1->SQR1 &= ~ADC_SQR1_L_Msk;               // Sequence length = 1 conversion
    ADC1->SQR1 &= ~ADC_SQR1_SQ1_Msk;
    ADC1->SQR1 |=  (5U << ADC_SQR1_SQ1_Pos);     // Channel 5 = PA0

    // Set longer sample time for Channel 5 (247.5 cycles) for stable high-impedance sensor readings
    ADC1->SMPR1 &= ~ADC_SMPR1_SMP5_Msk;
    ADC1->SMPR1 |=  (6U << ADC_SMPR1_SMP5_Pos);

    // 7. Enable ADC and wait until ready
    ADC1->ISR |= ADC_ISR_ADRDY;
    ADC1->CR  |= ADC_CR_ADEN;
    while (!(ADC1->ISR & ADC_ISR_ADRDY));
}

int32_t get_moisture_percent(uint32_t raw_adc)
{

    int32_t percent = ((ADC_DRY - (int32_t)raw_adc) * 100) / (ADC_DRY - ADC_WET);

    if (percent > 100) {
        percent = 100;
    } else if (percent < 0) {
        percent = 0;
    }
    return percent;
}

uint32_t adc_read(void)
{
    ADC1->CR |= ADC_CR_ADSTART;           // Start conversion
    while (!(ADC1->ISR & ADC_ISR_EOC));   // Wait for End of Conversion
    return ADC1->DR;                      // Read 12-bit result (0 - 4095)
}

int main(void)
{
    uart_init();
    adc_init();
    for (;;) {
        for(uint32_t i; i <= 10000000; i++) {
            ;
        }
        uint32_t raw = adc_read();
        // uart_print_num((int)raw);
        // uint32_t moisture = get_moisture_percent(raw);
        // uart_print("Moisture level: ");
        // uart_print_num((int)moisture);
        uart_print("\r\n");
   }
}
