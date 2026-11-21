#include <stdint.h>
#include <../include/stm32l476xx.h>

#define ADC_DRY 2400  // Replace with your measured dry air ADC value
#define ADC_WET 1200

#define DHT_PIN       0U
#define DHT_PIN_MASK  (1U << DHT_PIN)

#define CPU_HZ        4000000U
#define DHT_TIMEOUT_US 100U

void dht_timer_init(void) {
	// Enable the Cortex-M4 cycle counter
	CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;

	DWT->CYCCNT = 0;
	DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

void delay_us(uint32_t us) {
	uint32_t start = DWT->CYCCNT;
	uint32_t cycles = us * (CPU_HZ / 1000000U);

	while ((uint32_t) (DWT->CYCCNT - start) < cycles)
		;
}

void delay_ms(uint32_t ms) {
	while (ms--) {
		delay_us(1000);
	}
}

void dht_gpio_init(void) {
	// Enable GPIOA clock
	RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN;

	// PA0 initially input
	GPIOA->MODER &= ~GPIO_MODER_MODE0_Msk;

	// Open-drain output when driving the line
	GPIOA->OTYPER |= DHT_PIN_MASK;

	// No internal pull-up/down
	GPIOA->PUPDR &= ~GPIO_PUPDR_PUPD0_Msk;
}

// Wait for PA0 to reach the requested level.
// Returns 1 if successful, 0 on timeout.
int dht_wait_level(uint8_t level, uint32_t timeout_us) {
	uint32_t start = DWT->CYCCNT;
	uint32_t timeout_cycles = timeout_us * (CPU_HZ / 1000000U);

	while (((GPIOA->IDR & DHT_PIN_MASK) != 0) != level) {
		if ((uint32_t) (DWT->CYCCNT - start) >= timeout_cycles) {
			return 0;
		}
	}

	return 1;
}

int dht_read(uint8_t data[5]) {
	uint32_t start;
	uint32_t pulse_cycles;

	// Send start signal: pull DATA low for at least 18 ms
	GPIOA->MODER &= ~GPIO_MODER_MODE0_Msk;
	GPIOA->MODER |= GPIO_MODER_MODE0_0;

	GPIOA->BRR = DHT_PIN_MASK;

	delay_ms(18);

	// Release the line by switching PA0 to input
	GPIOA->MODER &= ~GPIO_MODER_MODE0_Msk;

	delay_us(30);

	// DHT11 response:
	// 80 us low, 80 us high, then 50 us low
	if (!dht_wait_level(0, DHT_TIMEOUT_US))
		return 0;

	if (!dht_wait_level(1, DHT_TIMEOUT_US))
		return 0;

	if (!dht_wait_level(0, DHT_TIMEOUT_US))
		return 0;

	// Read 40 bits (5 bytes)
	for (int i = 0; i < 5; i++) {
		data[i] = 0;

		for (int bit = 0; bit < 8; bit++) {
			// Each bit starts with a high pulse
			if (!dht_wait_level(1, DHT_TIMEOUT_US))
				return 0;

			start = DWT->CYCCNT;

			// Wait for the high pulse to end
			if (!dht_wait_level(0, DHT_TIMEOUT_US))
				return 0;

			pulse_cycles = DWT->CYCCNT - start;

			// At 4 MHz:
			// 26-28 us = bit 0
			// approximately 70 us = bit 1
			data[i] <<= 1;

			if (pulse_cycles > (50U * (CPU_HZ / 1000000U))) {
				data[i] |= 1;
			}
		}
	}

	// Check checksum
	uint8_t checksum = data[0] + data[1] + data[2] + data[3];

	if (checksum != data[4])
		return 0;

	return 1;
}

void delay_cycles(volatile uint32_t count) {
	while (count--) {
		__NOP();
	}
}
void uart_init(void) {
	// Enable GPIOA and USART2 clocks
	RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN;
	RCC->APB1ENR1 |= RCC_APB1ENR1_USART2EN;

	// 2. PA2 (TX) and PA3 (RX) to Alternate Function mode (10)
	GPIOA->MODER &= ~(GPIO_MODER_MODE2_Msk | GPIO_MODER_MODE3_Msk);
	GPIOA->MODER |= (GPIO_MODER_MODE2_1 | GPIO_MODER_MODE3_1);

	// 3. Select AF7 (USART2) for PA2 and PA3
	GPIOA->AFR[0] &= ~(GPIO_AFRL_AFSEL2_Msk | GPIO_AFRL_AFSEL3_Msk);
	GPIOA->AFR[0] |= ((7U << GPIO_AFRL_AFSEL2_Pos)
			| (7U << GPIO_AFRL_AFSEL3_Pos));

	// 4. Configure 9600 baud @ 4 MHz default MSI clock (4000000 / 9600 = 417)
	USART2->CR1 = 0;
	USART2->BRR = 4000000U / 9600U;

	// 5. Enable USART2, Transmitter, and Receiver
	USART2->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
}

void uart_putc(char c) {
	while (!(USART2->ISR & USART_ISR_TXE))
		;
	USART2->TDR = c;
}

char uart_getc(void) {
	while (!(USART2->ISR & (1U << 5)))
		;

	return (char) USART2->RDR;
}

void uart_print(const char *str) {
	while (*str)
		uart_putc(*str++);
}

void uart_print_num(int n) {
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

void adc_init(void) {
	// 1. Enable GPIOA and ADC clocks
	RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN | RCC_AHB2ENR_ADCEN;

	// 2. Select System Clock (4 MHz) as ADC clock source
	RCC->CCIPR &= ~RCC_CCIPR_ADCSEL_Msk;
	RCC->CCIPR |= (3U << RCC_CCIPR_ADCSEL_Pos);

	// 3. Set PA0 to Analog Mode (11) and close analog switch (ASCR)
	GPIOA->MODER |= (GPIO_MODER_MODE0_0 | GPIO_MODER_MODE0_1);
	GPIOA->ASCR |= GPIO_ASCR_ASC0; // Required on STM32L476xx for ADC analog input

	// 4. Exit Deep Power-Down mode and enable ADC internal voltage regulator
	ADC1->CR &= ~ADC_CR_DEEPPWD;
	ADC1->CR |= ADC_CR_ADVREGEN;
	for (volatile int i = 0; i < 1000; i++)
		; // Wait ~20 us for regulator startup

	// 5. Calibrate ADC (Single-Ended mode)
	ADC1->CR &= ~ADC_CR_ADCALDIF;
	ADC1->CR |= ADC_CR_ADCAL;
	while (ADC1->CR & ADC_CR_ADCAL)
		;

	// 6. Configure Channel 5 (PA0) as 1st conversion in regular sequence
	ADC1->SQR1 &= ~ADC_SQR1_L_Msk;             // Sequence length = 1 conversion
	ADC1->SQR1 &= ~ADC_SQR1_SQ1_Msk;
	ADC1->SQR1 |= (5U << ADC_SQR1_SQ1_Pos);     // Channel 5 = PA0

	// Set longer sample time for Channel 5 (247.5 cycles) for stable high-impedance sensor readings
	ADC1->SMPR1 &= ~ADC_SMPR1_SMP5_Msk;
	ADC1->SMPR1 |= (6U << ADC_SMPR1_SMP5_Pos);

	// 7. Enable ADC and wait until ready
	ADC1->ISR |= ADC_ISR_ADRDY;
	ADC1->CR |= ADC_CR_ADEN;
	while (!(ADC1->ISR & ADC_ISR_ADRDY))
		;
}

int32_t get_moisture_percent(uint32_t raw_adc) {

	int32_t percent = ((ADC_DRY - (int32_t) raw_adc) * 100)
			/ (ADC_DRY - ADC_WET);

	if (percent > 100) {
		percent = 100;
	} else if (percent < 0) {
		percent = 0;
	}
	return percent;
}

uint32_t adc_read(void) {
	ADC1->CR |= ADC_CR_ADSTART;           // Start conversion
	while (!(ADC1->ISR & ADC_ISR_EOC))
		;   // Wait for End of Conversion
	return ADC1->DR;                      // Read 12-bit result (0 - 4095)
}

int main(void) {
	uart_init();
	adc_init();
	uint8_t dht_data[5];

	uart_init();
	dht_timer_init();
	dht_gpio_init();

	uart_print("DHT11 sensor starting...\r\n");
	for (;;) {
		for (uint32_t i; i <= 10000000; i++) {
			;
		}
		uint32_t raw = adc_read();
		uart_print_num((int)raw);
		uint32_t moisture = get_moisture_percent(raw);
		uart_print("Moisture level: ");
		uart_print_num((int)moisture);
		uart_print("\r\n");
		//dht
		if (dht_read(dht_data)) {
			uint8_t humidity = dht_data[0];
			uint8_t temperature = dht_data[2];

			uart_print("Temperature: ");
			uart_print_num(temperature);
			uart_print(" C\r\n");

			uart_print("Humidity: ");
			uart_print_num(humidity);
			uart_print(" %\r\n");

			uart_print("----------------\r\n");
		} else {
			uart_print("DHT11 read error\r\n");
		}

		// DHT11 should not be read too frequently
		delay_ms(2000);
	}
}
