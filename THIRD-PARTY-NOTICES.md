# Third-party assets

The supplied game uses Creepster and Oswald. Local font copies preserve its
appearance without runtime network requests.

## Creepster

- Font project: https://github.com/google/fonts/tree/main/ofl/creepster
- Downloaded from Google Fonts: https://fonts.gstatic.com/s/creepster/v13/AlZy_zVUqJz4yMrniH4hdQ.ttf
- License: SIL Open Font License 1.1, reproduced in `fonts/Creepster-OFL.txt`.
- Font data is unmodified.

## Oswald

- Font project: https://github.com/google/fonts/tree/main/ofl/oswald
- Downloaded from Google Fonts, regular/semibold/bold:
  - https://fonts.gstatic.com/s/oswald/v57/TK3_WkUHHAIjg75cFRf3bXL8LICs1_FvgUE.ttf
  - https://fonts.gstatic.com/s/oswald/v57/TK3_WkUHHAIjg75cFRf3bXL8LICs1y9ogUE.ttf
  - https://fonts.gstatic.com/s/oswald/v57/TK3_WkUHHAIjg75cFRf3bXL8LICs1xZogUE.ttf
- License: SIL Open Font License 1.1, reproduced in `fonts/Oswald-OFL.txt`.
- Font data is unmodified.

Game sound effects are synthesized with the browser's Web Audio API; no audio
recordings are bundled. The supplied game has not been assigned a new license.

## QR Code Generator

- Project: https://github.com/kazuhikoarase/qrcode-generator
- Pinned source commit: `83b7e8fe3fddd3b0368dbafd6ce56995bd25e3c8`.
- Unmodified JavaScript: `assets/vendor/qrcode.js` (upstream `js/dist/qrcode.js`).
- MIT license reproduced in `assets/vendor/qrcode-LICENSE.txt`.
- Used locally to generate phone pairing codes; no online QR service is used.
