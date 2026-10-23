; friends module NASC URL. ReviveShop answers NASC on Flask :8000 (/ac/).
; NOTE: http:C already rewrites nasc.* -> box:8000, so this is normally
; redundant. Kept as a belt-and-braces fallback (adapted from
; PretendoNetwork/nimbus). Offset is for the common retail friends module.
;
; Replace RS_NASC_URL at build time with "[https|http]://<RS_HOST>/ac/".

.org 0x16129a
  .area 38
    .asciiz "https://192.168.4.34:8000/ac/"
  .endarea
