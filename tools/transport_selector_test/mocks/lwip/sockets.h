#pragma once

#include <stddef.h>

#ifndef MSG_DONTWAIT
#define MSG_DONTWAIT 0x40
#endif

int mock_socket_send(int fd, const void* data, size_t len, int flags);
#define send mock_socket_send
