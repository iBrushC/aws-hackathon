#pragma once

/* =========================================================================
 *  Camera pin map — Seeed XIAO ESP32S3 Sense expansion board
 *
 *  Self-contained on purpose. The Arduino ESP32 core ships a camera_pins.h,
 *  but only inside the CameraWebServer *example* folder, so it is not on the
 *  include path for your own sketch. Rather than depend on a file you have to
 *  download and keep in sync, the pins are just written out here.
 *
 *  These are the DVP lines the camera connector occupies on the Sense board
 *  (14 GPIOs). Identical for the stock OV2640 and the OV5640 upgrade — same
 *  parallel interface, only the sensor behind it differs.
 *
 *  Note the pins NOT listed: the board has no PWDN or RESET line broken out,
 *  hence -1 for both. That is correct, not a placeholder.
 * ========================================================================= */

#define PWDN_GPIO_NUM     -1   /* not wired on this board */
#define RESET_GPIO_NUM    -1   /* not wired on this board */

#define XCLK_GPIO_NUM     10   /* XMCLK */
#define SIOD_GPIO_NUM     40   /* CAM_SDA — SCCB data  */
#define SIOC_GPIO_NUM     39   /* CAM_SCL — SCCB clock */

#define Y9_GPIO_NUM       48   /* DVP_Y9  (MSB) */
#define Y8_GPIO_NUM       11   /* DVP_Y8  */
#define Y7_GPIO_NUM       12   /* DVP_Y7  */
#define Y6_GPIO_NUM       14   /* DVP_Y6  */
#define Y5_GPIO_NUM       16   /* DVP_Y5  */
#define Y4_GPIO_NUM       18   /* DVP_Y4  */
#define Y3_GPIO_NUM       17   /* DVP_Y3  */
#define Y2_GPIO_NUM       15   /* DVP_Y2  (LSB) */

#define VSYNC_GPIO_NUM    38   /* DVP_VSYNC */
#define HREF_GPIO_NUM     47   /* DVP_HREF  */
#define PCLK_GPIO_NUM     13   /* DVP_PCLK  */

/* Deliberately no LED_GPIO_NUM here.
 *
 * The stock core header defines it as 21 for this board, but 21 is also the
 * microSD chip-select on the Sense expansion board (SD_PIN_CS in config.h).
 * Anything that drives it as a flash LED will fight the card. If you want a
 * flash, move SD CS to a free pin first. */
