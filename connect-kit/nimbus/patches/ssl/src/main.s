; ReviveShop SSL sysmodule patch (0004013000002F02).
;
; Disables Root CA verification in the 3DS SSL module so the console will
; accept the ReviveShop dev certificates (self-signed) without installing a
; CA on the console. This is what lets the console talk to local ReviveShop
; servers over HTTPS with no per-console certificate setup.
;
; Adapted from TraceEntertains/3DS-SSL-Patch and SciresM/3DS-SSL-Patch.
;
; Build needs: the decrypted+decompressed SSL sysmodule code binary as
; code.bin, alongside this file. Then `make` -> out/code.ips.
;
;   install to: sdcard:/luma/sysmodules/0004013000002F02.ips
;   Luma3DS:    enable "Enable game patching"
;
; NOTE: we already ship a prebuilt copy of this patch at
;        connect-kit/0004013000002F02.ips
; It is byte-identical in shape (one 24-byte write at 0x6c56). This source is
; here so we can rebuild/verify it.

.3ds
.thumb

.open "code.bin", "build/patched_code.bin", 0x100000

jmp_addr equ 0x106C72

.org 0x106C56
main:
    add r7, r4, #7
    add r7, #0xf9
    sub r2, r7, r4
    add r0, r2, r2
    add r0, #0x1b
    orr r5, r0
    str r5, [r7,#0x28]
    cmp r6, #0
    beq jmp_addr
    mov r0, r4
    add r0, #0x20
    mov r1, r6

.close
