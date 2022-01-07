#!/usr/bin/env python3

# Created by Don Barber, don@dgb3.net
# Pass the raw disk image on the command line as argument 1
# add verbose as argument 2 if you want some extra details

# MFS implementation details from https://www.macgui.com/news/article.php?t = 482

# If the image is a diskcopy 4.2 image, extract the raw MFS image first via:
#  dd if = INPUTFILE of = OUTPUTFILE bs = 84 skip = 1

# Idea for improvement: extract files as macbinary format instead of
# individual data and resource forks

import os
import math
from binascii import crc_hqx
from struct import pack, unpack
from sys import argv


def file_to_macbin(data, rsrc, crdate, mddate, type, creator, flags, name):
    oldFlags = flags >> 8
    newFlags = flags & 255
    macbin = pack(
        ">x64p4s4sB7xBxIIII2xB14x6xBB",
        name,
        type,
        creator,
        oldFlags,
        oldFlags & 128,
        len(data),
        len(rsrc),
        crdate,
        mddate,
        newFlags,
        129,
        129,
    )
    macbin += pack(">H2x", crc_hqx(macbin, 0))
    if data:
        macbin += data
        macbin += b"\x00" * (-len(data) % 128)

    if rsrc:
        macbin += rsrc
        macbin += b"\x00" * (-len(rsrc) % 128)

    return macbin


filename = argv[1]

file_size = os.path.getsize(filename)
fh = open(filename, "rb")

fh.seek(1026)

(
    drCrDate,
    drLsBkUp,
    drAtrb,
    drNmFls,
    drDirSt,
    drBlLen,
    drNmAlBlks,
    drAlBlkSiz,
    drClpSiz,
    drAlBlSt,
    drNxtFNum,
    drFreeBks,
    drVNl,
) = unpack(">IIHHHHHIIHIHB", fh.read(35))

drVN = fh.read(drVNl).decode("mac-roman")
print(f"Volume Name: {drVN}")
if "verbose" in argv:
    print(f"Volume Create Datestamp: {drCrDate}")
    print(f"Volume Modify Datestamp: {drLsBkUp}")

maplocation = 0x440


def getmapentry(blocknum):
    location = (blocknum - 2) * 12 / 8
    if location == math.ceil(location):
        fh.seek(maplocation + int(location))
        entry = unpack(">H", fh.read(2))[0] >> 4
    else:
        fh.seek(maplocation + math.floor(location))
        entry = unpack(">H", fh.read(2))[0] & 0xFFF
    return entry


def getfilecontents(block, length):
    blocklist = [block]
    while True:
        block = getmapentry(block)
        # print(block)
        if block == 1:
            break
        blocklist.append(block)
        if block == 0:
            raise Exception("Unused Block")

    if "verbose" in argv:
        print("Blocklist:", blocklist)

    contents = b""
    for block in blocklist:
        if "verbose" in argv:
            print(
                f"Seeking to: {drAlBlSt * 512 + (block - 2) * drAlBlkSiz:x} for block {block}"
            )
        fh.seek(drAlBlSt * 512 + (block - 2) * drAlBlkSiz)
        data = fh.read(drAlBlkSiz)
        contents += data

    return contents[:length]


fh.seek(drDirSt * 512)
while True:
    flFlgs = fh.read(1)
    flType = int.from_bytes(fh.read(1), "big")
    while flFlgs == b"\x00":  # loop until next record found
        flFlgs = fh.read(1)
        flType = int.from_bytes(fh.read(1), "big")
        if fh.tell() >= (
            (drDirSt + drBlLen - 1) * 512
        ):  # we're past the end of the file directory, exit out
            break

    if fh.tell() >= (
        (drDirSt + drBlLen - 1) * 512
    ):  # we're past the end of the file directory, exit out
        break

    if flFlgs != b"\x00":
        # flUsrWds = fh.read(16)
        fdType, fdCreator, fdFlags, fdLocation, fdFldr = unpack(">4s4sHIh", fh.read(16))
        (
            flFlNum,
            flStBlk,
            flLgLen,
            flPyLen,
            flRStBlk,
            flRLgLen,
            flRPyLen,
            flCrDat,
            flMdDat,
            flNaml,
        ) = unpack(">IHIIHIIIIB", fh.read(33))
        flNam = fh.read(flNaml)
        fh.read(fh.tell() % 2)  # align to word boundary after reading name
        if flFlNum != 0:
            print(hex(fh.tell()), flFlNum, flNaml, flNam.decode("mac-roman"))
            if "verbose" in argv:
                print(f"Create Datestamp: {flCrDat}")
                print(f"Modify Datestamp: {flMdDat}")

            location = fh.tell()

            if not flStBlk and not flRStBlk:
                print(
                    f'Error: {flNam.decode("mac-roman")} has neither data nor resource fork'
                )
                continue

            if flStBlk != 0:
                datafrk = getfilecontents(flStBlk, flLgLen)
            else:
                datafrk = b""

            if flRStBlk != 0:
                rsrcfrk = getfilecontents(flRStBlk, flRLgLen)
            else:
                rsrcfrk = b""

            with open(flNam.decode("mac-roman"), "wb") as oh:
                # if not rsrcfrk:
                #     oh.write(datafrk)
                # else:
                oh.write(
                    file_to_macbin(
                        datafrk,
                        rsrcfrk,
                        flCrDat,
                        flMdDat,
                        fdType,
                        fdCreator,
                        fdFlags,
                        flNam,
                    )
                )

            fh.seek(location)

fh.close()
