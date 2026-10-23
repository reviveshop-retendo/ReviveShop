; act (account) module URL. ReviveShop's ReTendo account server answers on
; Flask :8000 (/v1/api/), so we always pick the local URL regardless of the
; console's server-type. Adapted from PretendoNetwork/nimbus (environment
; check removed). Offsets are for the common retail act module.
;
; Replace the URL at build time with "https://<RS_HOST>:8000/v1/api/".

frd_get_server_types equ 0x105340
set_base_account_url equ 0x10ed48

.org 0x10e4f8
  .area 152
    get_account_url:
      push { r0, r1, r2, r3, r4, lr }
      mov r4, r0 ; copy url pointer to r4
      ldr r1, =unofficial_url
      mov r2, #0x0
      add r0, r4, #0x4
      bl set_base_account_url
      mov r0, #0x0
      pop { r0, r1, r2, r3, r4, pc }

    .align 4
    unofficial_url:
      .asciiz "https://192.168.4.34:8000/v1/api/"

    .pool
  .endarea
