#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef struct {
    char issuer[40], name[16], serial[16];
    unsigned int device_version, standard_version, asym[2], sym, hash, buffer_size;
} DeviceInfo;

static unsigned int step(const char *name) {
    const char *trace = getenv("SANSEC_TEST_TRACE");
    if (trace) {
        FILE *file = fopen(trace, "a");
        fprintf(file, "%s\n", name);
        fclose(file);
    }
    const char *hang = getenv("SANSEC_TEST_HANG");
    if (hang && !strcmp(hang, name)) sleep(60);
    const char *crash = getenv("SANSEC_TEST_CRASH");
    if (crash && !strcmp(crash, name)) _exit(17);
    const char *fail = getenv("SANSEC_TEST_FAIL");
    return fail && !strcmp(fail, name) ? strtoul(getenv("SANSEC_TEST_CODE"), NULL, 0) : 0;
}

unsigned int SDF_OpenDevice(void **device) {
    unsigned int code = step("open");
    if (!code) *device = (void *) 0x12345678abcdef00UL;
    return code;
}

unsigned int SDF_OpenSession(void *device, void **session) {
    if (device != (void *) 0x12345678abcdef00UL) return 1;
    unsigned int code = step("session");
    if (!code) *session = (void *) 0x23456789abcdef00UL;
    return code;
}

unsigned int SDF_GetDeviceInfo(void *session, DeviceInfo *info) {
    if (session != (void *) 0x23456789abcdef00UL) return 1;
    const char *serial = getenv("SANSEC_TEST_SERIAL");
    strncpy(info->serial, serial ? serial : "TEST-SERIAL", 16);
    info->hash = 1;
    return step("info");
}

unsigned int SDF_GetFirmwareVersion(void *session, char *buffer, unsigned int *length) {
    strcpy(buffer, "test-firmware");
    *length = strlen(buffer);
    return step("firmware");
}

unsigned int SDF_GetLibraryVersion(void *session, char *buffer, unsigned int *length) {
    strcpy(buffer, "test-library");
    *length = strlen(buffer);
    return step("library");
}

unsigned int SDF_HashInit(void *session, unsigned int algorithm, void *key, void *id, unsigned int length) {
    if (algorithm != 1 || key || id || length) return 1;
    return step("init");
}

unsigned int SDF_HashUpdate(void *session, char *data, unsigned int length) {
    if (length != 3 || memcmp(data, "abc", 3)) return 1;
    return step("update");
}

unsigned int SDF_HashFinal(void *session, unsigned char *digest, unsigned int *length) {
    const unsigned char expected[32] = {
        0x66, 0xc7, 0xf0, 0xf4, 0x62, 0xee, 0xed, 0xd9, 0xd1, 0xf2, 0xd4, 0x6b, 0xdc, 0x10, 0xe4, 0xe2,
        0x41, 0x67, 0xc4, 0x87, 0x5c, 0xf2, 0xf7, 0xa2, 0x29, 0x7d, 0xa0, 0x2b, 0x8f, 0x4b, 0xa8, 0xe0
    };
    memcpy(digest, expected, 32);
    *length = 32;
    if (getenv("SANSEC_TEST_BAD_HASH")) digest[0] ^= 1;
    return step("final");
}

unsigned int SDF_CloseSession(void *session) { return step("close_session"); }
unsigned int SDF_CloseDevice(void *device) { return step("close_device"); }
