; ReviveShop http:C sysmodule URL redirect.
;
; Mirrors PretendoNetwork/nimbus' patches/http (MIT), with two changes:
;   1. the NASC-environment check is removed, so the redirect always applies
;      (ReviveShop has no separate "test" account);
;   2. the replacement table maps Nintendo hostnames onto the ReviveShop box
;      as `IP:PORT`, so the console connects straight to the local servers
;      with no proxy setting and no DNS override needed.
;
; Requires the decrypted+decompressed http:C (000401300000AE02) code binary as
; code.bin. Offsets below are the common retail http:C layout (same as Nimbus).
;
;   install to: sdcard:/luma/sysmodules/000401300000AE02.ips
;   Luma3DS:    enable "Enable game patching"
;
; Build-time config: RS_HOST is the box's LAN address (see hosts.conf / build.sh).

.3ds

.open "code.bin", "build/patched_code.bin", 0x100000

;                                   (r0)              (r1)
; Result get_service_handle(Handle* handle_out, char* service_name)
get_service_handle equ 0x10DB40

;                    (r0)       (r1)        (r2)
; void* memcpy(void* dst, void* src, size_t size)
memcpy equ 0x10D2DC

;                     (r0)
; size_t strlen(char* string)
strlen equ 0x10F8B0

replace_hook_addr equ 0x113868
replace_function_addr equ 0x11AA70

.org replace_hook_addr
	replace_hook:
		bl replace_func_jump

.org replace_function_addr
	replace_func_jump:
		mov     r0, r5
		b       handle_replacements

	.include "src/strfunctions.s"

	;                                                         (r0)                     (r1)          (r2)
	; returns modified char* in r0, func variables are (char* stringToReplaceOn, char* target, char* replacement)
	find_and_replace:
		push    {r11, lr}
		add     r11, sp, #4
		sub     sp, sp, #0x20
		str     r0, [r11, #-0x18]
		str     r1, [r11, #-0x1c]
		str     r2, [r11, #-0x20]
		ldr     r1, [r11, #-0x1c]
		ldr     r0, [r11, #-0x18]
		bl      strstr
		str     r0, [r11, #-8]
		ldr     r3, [r11, #-8]
		cmp     r3, #0
		beq     find_and_replace_lab_1
		ldr     r0, [r11, #-0x1c]
		bl      strlen
		mov     r3, r0
		str     r3, [r11, #-0xc]
		ldr     r0, [r11, #-0x20]
		bl      strlen
		mov     r3, r0
		str     r3, [r11, #-0x10]
		ldr     r3, [r11, #-0xc]
		ldr     r2, [r11, #-8]
		add     r3, r2, r3
		mov     r0, r3
		bl      strlen
		mov     r3, r0
		str     r3, [r11, #-0x14]
		ldr     r3, [r11, #-0x10]
		ldr     r2, [r11, #-8]
		add     r0, r2, r3
		ldr     r3, [r11, #-0xc]
		ldr     r2, [r11, #-8]
		add     r1, r2, r3
		ldr     r3, [r11, #-0x14]
		add     r3, r3, #1
		mov     r2, r3
		bl      memcpy
		ldr     r2, [r11, #-0x10]
		ldr     r1, [r11, #-0x20]
		ldr     r0, [r11, #-8]
		bl      memcpy
		b       find_and_replace_lab_2

	find_and_replace_lab_1:
		mov     r0, r0

	find_and_replace_lab_2:
		sub     sp, r11, #4
		pop     {r11, lr}
		bx      lr

	; One entry per host. r11-0x28 holds the URL string.
	; (real instruction sequences live in src/replacements.s, generated)
	handle_replacements:
		push    {r11, lr}
		add     r11, sp, #4
		sub     sp, sp, #0x28
		str     r0, [r11, #-0x28]
		.include "src/replacements.s"
	.align 2
	handle_replacements_end:
		mov     r0, r0
		mov     r0, r3
		sub     sp, r11, #4
		pop     {r11, lr}
		bx      lr

	.include "src/strings.s"

	.pool

.close
