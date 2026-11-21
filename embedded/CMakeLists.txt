cmake_minimum_required(VERSION 3.20)

project(stm32_blink C ASM)

set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR cortex-m4)

set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
set(CMAKE_OBJCOPY arm-none-eabi-objcopy)

set(CMAKE_C_FLAGS
    "-mcpu=cortex-m4 -mthumb -O0 -ffreestanding -fdata-sections -ffunction-sections"
)

set(CMAKE_ASM_FLAGS
    "-mcpu=cortex-m4 -mthumb"
)

set(CMAKE_EXE_LINKER_FLAGS
    "-mcpu=cortex-m4 -mthumb -nostdlib -Wl,--gc-sections -T${CMAKE_SOURCE_DIR}/linker.ld"
)

add_executable(blink.elf
    main.c
    startup.s
)

set_target_properties(blink.elf PROPERTIES
    SUFFIX ""
)

add_custom_command(TARGET blink.elf POST_BUILD
    COMMAND ${CMAKE_OBJCOPY}
        -O binary
        $<TARGET_FILE:blink.elf>
        ${CMAKE_BINARY_DIR}/blink.bin
)
