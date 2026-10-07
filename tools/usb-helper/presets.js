/* Offline MeshCoreTel city presets. Updated only by the release maintainer. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SmartUiPresets = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const snapshot = /* SMARTUI_PRESETS_DATA_BEGIN */
{
  "metadata": {
    "schema": 1,
    "snapshotAt": "2026-10-07T06:07:21.505Z",
    "sourceUrl": "https://meshcoretel.ru/ru/OMS",
    "sourceName": "MeshCoreTel",
    "countrySelection": "RU",
    "selectionCount": 55,
    "presetCount": 55,
    "excluded": [],
    "catalogUrl": "https://meshcoretel.ru/api/regions/catalog",
    "radioUrl": "https://meshcoretel.ru/api/regions/radio-settings?all_regions=true",
    "namesUrl": "https://meshcoretel.ru/assets/index-CVGmAzTM.js",
    "sourceHashes": {
      "catalog": "0e04011aa7be8f8155af1d67ff8ef0ceb97dea0f4daf4df068302d69817d1e83",
      "radio": "c3510c53d7d9f565f4beae0f8a94e83fb366d5010eb075cf533abd545aec176b",
      "names": "d7ae6dcb53c5404149f6366decda23c6dd8bbd9c92ec0b1ffc346c57b3164c70"
    },
    "selectionPolicy": "Only RU iata regions listed in the source catalog; exact radio code match. No client default.",
    "unknownFields": [
      "votes",
      "sourceUpdatedAt",
      "pathHashBytes"
    ]
  },
  "presets": [
    {
      "id": "ANG",
      "code": "ANG",
      "name": "Ангарск",
      "nameEn": "Angarsk",
      "frequencyKHz": 869618,
      "frequencyMHz": 869.618,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 8,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/ANG",
      "sourceRadio": {
        "frequency": "869.617981",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "8"
      }
    },
    {
      "id": "ASF",
      "code": "ASF",
      "name": "Астрахань",
      "nameEn": "Astrakhan",
      "frequencyKHz": 869525,
      "frequencyMHz": 869.525,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 8,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/ASF",
      "sourceRadio": {
        "frequency": "869.525024",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "8"
      }
    },
    {
      "id": "BSK",
      "code": "BSK",
      "name": "Бийск",
      "nameEn": "Biysk",
      "frequencyKHz": 869000,
      "frequencyMHz": 869,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 5,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/BSK",
      "sourceRadio": {
        "frequency": "869.000000",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "5"
      }
    },
    {
      "id": "BTK",
      "code": "BTK",
      "name": "Братск",
      "nameEn": "Bratsk",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/BTK",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "BZK",
      "code": "BZK",
      "name": "Брянск",
      "nameEn": "Bryansk",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/BZK",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "CEE",
      "code": "CEE",
      "name": "Череповец",
      "nameEn": "Cherepovets",
      "frequencyKHz": 868570,
      "frequencyMHz": 868.57,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 8,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/CEE",
      "sourceRadio": {
        "frequency": "868.570007",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "8"
      }
    },
    {
      "id": "CEK",
      "code": "CEK",
      "name": "Челябинск",
      "nameEn": "Chelyabinsk",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/CEK",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "CSY",
      "code": "CSY",
      "name": "Чебоксары",
      "nameEn": "Cheboksary",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 6,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/CSY",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "6"
      }
    },
    {
      "id": "DOK",
      "code": "DOK",
      "name": "Донецк",
      "nameEn": "Donetsk",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/DOK",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "7"
      }
    },
    {
      "id": "EGO",
      "code": "EGO",
      "name": "Белгород",
      "nameEn": "Belgorod",
      "frequencyKHz": 868825,
      "frequencyMHz": 868.825,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/EGO",
      "sourceRadio": {
        "frequency": "868.825012",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "EYK",
      "code": "EYK",
      "name": "Белоярский",
      "nameEn": "Beloyarsky",
      "frequencyKHz": 869618,
      "frequencyMHz": 869.618,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 5,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/EYK",
      "sourceRadio": {
        "frequency": "869.617981",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "5"
      }
    },
    {
      "id": "GDX",
      "code": "GDX",
      "name": "Магадан",
      "nameEn": "Magadan",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/GDX",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "GOJ",
      "code": "GOJ",
      "name": "Нижний Новгород",
      "nameEn": "Nizhny Novgorod",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 6,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/GOJ",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "6"
      }
    },
    {
      "id": "GSV",
      "code": "GSV",
      "name": "Саратов",
      "nameEn": "Saratov",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 5,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/GSV",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "5"
      }
    },
    {
      "id": "GVK",
      "code": "GVK",
      "name": "GVK",
      "nameEn": "GVK",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/GVK",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "7"
      }
    },
    {
      "id": "IAR",
      "code": "IAR",
      "name": "Ярославль",
      "nameEn": "Tunoshna",
      "frequencyKHz": 869150,
      "frequencyMHz": 869.15,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/IAR",
      "sourceRadio": {
        "frequency": "869.150024",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "IKT",
      "code": "IKT",
      "name": "Иркутск",
      "nameEn": "Irkutsk",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/IKT",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "IWA",
      "code": "IWA",
      "name": "Иваново",
      "nameEn": "Ivanovo",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 8,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/IWA",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "8"
      }
    },
    {
      "id": "KHV",
      "code": "KHV",
      "name": "Хабаровск",
      "nameEn": "Khabarovsk",
      "frequencyKHz": 864281,
      "frequencyMHz": 864.281,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/KHV",
      "sourceRadio": {
        "frequency": "864.281006",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "KJA",
      "code": "KJA",
      "name": "Красноярск",
      "nameEn": "Krasnoyarsk",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/KJA",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "KLD",
      "code": "KLD",
      "name": "Тверь",
      "nameEn": "Tver",
      "frequencyKHz": 869169,
      "frequencyMHz": 869.169,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 8,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/KLD",
      "sourceRadio": {
        "frequency": "869.169006",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "8"
      }
    },
    {
      "id": "KLF",
      "code": "KLF",
      "name": "Калуга",
      "nameEn": "Kaluga",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/KLF",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "KUF",
      "code": "KUF",
      "name": "Самара",
      "nameEn": "Samara",
      "frequencyKHz": 864281,
      "frequencyMHz": 864.281,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/KUF",
      "sourceRadio": {
        "frequency": "864.281006",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "7"
      }
    },
    {
      "id": "KVK",
      "code": "KVK",
      "name": "Апатиты",
      "nameEn": "Apatity",
      "frequencyKHz": 867670,
      "frequencyMHz": 867.67,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/KVK",
      "sourceRadio": {
        "frequency": "867.67",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "KVX",
      "code": "KVX",
      "name": "Киров",
      "nameEn": "Kirov",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 8,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/KVX",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "8"
      }
    },
    {
      "id": "KZN",
      "code": "KZN",
      "name": "Казань",
      "nameEn": "Kazan",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 6,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/KZN",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "6"
      }
    },
    {
      "id": "LED",
      "code": "LED",
      "name": "Санкт-Петербург",
      "nameEn": "St. Petersburg",
      "frequencyKHz": 868856,
      "frequencyMHz": 868.856,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/LED",
      "sourceRadio": {
        "frequency": "868.856018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "LNX",
      "code": "LNX",
      "name": "Смоленск",
      "nameEn": "Smolensk",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 8,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/LNX",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "8"
      }
    },
    {
      "id": "LPK",
      "code": "LPK",
      "name": "Липецк",
      "nameEn": "Lipetsk",
      "frequencyKHz": 868950,
      "frequencyMHz": 868.95,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/LPK",
      "sourceRadio": {
        "frequency": "868.950012",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "7"
      }
    },
    {
      "id": "MCX",
      "code": "MCX",
      "name": "Махачкала",
      "nameEn": "Makhachkala",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/MCX",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "MOW",
      "code": "MOW",
      "name": "Москва",
      "nameEn": "Moscow",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/MOW",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "MQF",
      "code": "MQF",
      "name": "Магнитогорск",
      "nameEn": "Magnitogorsk",
      "frequencyKHz": 868763,
      "frequencyMHz": 868.763,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 6,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/MQF",
      "sourceRadio": {
        "frequency": "868.763000",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "6"
      }
    },
    {
      "id": "NUX",
      "code": "NUX",
      "name": "Новый Уренгой",
      "nameEn": "Novy Urengoy",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/NUX",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "OEL",
      "code": "OEL",
      "name": "Орёл",
      "nameEn": "Oakley",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/OEL",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "OMS",
      "code": "OMS",
      "name": "Омск",
      "nameEn": "Omsk",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/OMS",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "OVB",
      "code": "OVB",
      "name": "Новосибирск",
      "nameEn": "Novosibirsk",
      "frequencyKHz": 869000,
      "frequencyMHz": 869,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 8,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/OVB",
      "sourceRadio": {
        "frequency": "869.000000",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "8"
      }
    },
    {
      "id": "PEE",
      "code": "PEE",
      "name": "Пермь",
      "nameEn": "Perm",
      "frequencyKHz": 868733,
      "frequencyMHz": 868.733,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 6,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/PEE",
      "sourceRadio": {
        "frequency": "868.732971",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "6"
      }
    },
    {
      "id": "PEZ",
      "code": "PEZ",
      "name": "Пенза",
      "nameEn": "Penza",
      "frequencyKHz": 868918,
      "frequencyMHz": 868.918,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/PEZ",
      "sourceRadio": {
        "frequency": "868.918030",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "7"
      }
    },
    {
      "id": "ROV",
      "code": "ROV",
      "name": "Ростов-на-Дону",
      "nameEn": "Rostov-on-Don",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/ROV",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "7"
      }
    },
    {
      "id": "RZN",
      "code": "RZN",
      "name": "Рязань",
      "nameEn": "Ryazan",
      "frequencyKHz": 868880,
      "frequencyMHz": 868.88,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 5,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/RZN",
      "sourceRadio": {
        "frequency": "868.880005",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "5"
      }
    },
    {
      "id": "SVX",
      "code": "SVX",
      "name": "Екатеринбург",
      "nameEn": "Yekaterinburg",
      "frequencyKHz": 869047,
      "frequencyMHz": 869.047,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/SVX",
      "sourceRadio": {
        "frequency": "869.046997",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "TBW",
      "code": "TBW",
      "name": "Тамбов",
      "nameEn": "Tambov",
      "frequencyKHz": 868950,
      "frequencyMHz": 868.95,
      "bandwidthHz": 125000,
      "bandwidthKHz": 125,
      "sf": 10,
      "cr": 5,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/TBW",
      "sourceRadio": {
        "frequency": "868.950012",
        "bandwidth": "125.0",
        "spreadingFactor": "10",
        "codingRate": "5"
      }
    },
    {
      "id": "TGK",
      "code": "TGK",
      "name": "Таганрог",
      "nameEn": "Taganrog",
      "frequencyKHz": 868600,
      "frequencyMHz": 868.6,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/TGK",
      "sourceRadio": {
        "frequency": "868.599976",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "TJM",
      "code": "TJM",
      "name": "Тюмень",
      "nameEn": "Tyumen",
      "frequencyKHz": 869050,
      "frequencyMHz": 869.05,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/TJM",
      "sourceRadio": {
        "frequency": "869.049988",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "7"
      }
    },
    {
      "id": "TOF",
      "code": "TOF",
      "name": "Томск",
      "nameEn": "Tomsk",
      "frequencyKHz": 869106,
      "frequencyMHz": 869.106,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 5,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/TOF",
      "sourceRadio": {
        "frequency": "869.106018",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "5"
      }
    },
    {
      "id": "TYA",
      "code": "TYA",
      "name": "Тула",
      "nameEn": "Tula",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/TYA",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "7"
      }
    },
    {
      "id": "TYI",
      "code": "TYI",
      "name": "Тольятти",
      "nameEn": "Tolyatti",
      "frequencyKHz": 864281,
      "frequencyMHz": 864.281,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/TYI",
      "sourceRadio": {
        "frequency": "864.281006",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "7"
      }
    },
    {
      "id": "UFA",
      "code": "UFA",
      "name": "Уфа",
      "nameEn": "Ufa",
      "frequencyKHz": 869000,
      "frequencyMHz": 869,
      "bandwidthHz": 125000,
      "bandwidthKHz": 125,
      "sf": 11,
      "cr": 5,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/UFA",
      "sourceRadio": {
        "frequency": "869.000000",
        "bandwidth": "125.0",
        "spreadingFactor": "11",
        "codingRate": "5"
      }
    },
    {
      "id": "ULK",
      "code": "ULK",
      "name": "Ленск",
      "nameEn": "Lensk",
      "frequencyKHz": 869432,
      "frequencyMHz": 869.432,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 5,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/ULK",
      "sourceRadio": {
        "frequency": "869.432007",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "5"
      }
    },
    {
      "id": "ULV",
      "code": "ULV",
      "name": "Ульяновск",
      "nameEn": "Ulyanovsk",
      "frequencyKHz": 864281,
      "frequencyMHz": 864.281,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/ULV",
      "sourceRadio": {
        "frequency": "864.281006",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "7"
      }
    },
    {
      "id": "VLM",
      "code": "VLM",
      "name": "Владимир",
      "nameEn": "Vladimir",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 9,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/VLM",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "9",
        "codingRate": "7"
      }
    },
    {
      "id": "VOG",
      "code": "VOG",
      "name": "Волгоград",
      "nameEn": "Volgograd",
      "frequencyKHz": 869525,
      "frequencyMHz": 869.525,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/VOG",
      "sourceRadio": {
        "frequency": "869.525024",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "VOZ",
      "code": "VOZ",
      "name": "Воронеж",
      "nameEn": "Voronezh",
      "frequencyKHz": 868731,
      "frequencyMHz": 868.731,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 6,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/VOZ",
      "sourceRadio": {
        "frequency": "868.731018",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "6"
      }
    },
    {
      "id": "VSG",
      "code": "VSG",
      "name": "Луганск",
      "nameEn": "Lugansk",
      "frequencyKHz": 868825,
      "frequencyMHz": 868.825,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 7,
      "cr": 7,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/VSG",
      "sourceRadio": {
        "frequency": "868.825012",
        "bandwidth": "62.5",
        "spreadingFactor": "7",
        "codingRate": "7"
      }
    },
    {
      "id": "VVO",
      "code": "VVO",
      "name": "Владивосток",
      "nameEn": "Artyom",
      "frequencyKHz": 864281,
      "frequencyMHz": 864.281,
      "bandwidthHz": 62500,
      "bandwidthKHz": 62.5,
      "sf": 8,
      "cr": 8,
      "pathHashBytes": null,
      "votes": null,
      "sourceUpdatedAt": null,
      "sourceUrl": "https://meshcoretel.ru/ru/VVO",
      "sourceRadio": {
        "frequency": "864.281006",
        "bandwidth": "62.5",
        "spreadingFactor": "8",
        "codingRate": "8"
      }
    }
  ]
}
  /* SMARTUI_PRESETS_DATA_END */;
  const bandwidths = Object.freeze([7800, 10400, 15600, 20800, 31250, 41700, 62500, 125000, 250000, 500000]);

  function validateRadio(value) {
    return !!value && Number.isInteger(value.frequencyKHz) &&
      value.frequencyKHz >= 150000 && value.frequencyKHz <= 960000 &&
      bandwidths.includes(value.bandwidthHz) &&
      Number.isInteger(value.sf) && value.sf >= 5 && value.sf <= 12 &&
      Number.isInteger(value.cr) && value.cr >= 5 && value.cr <= 8 &&
      (value.pathHashBytes === null || [1, 2, 3].includes(value.pathHashBytes));
  }

  function freeze(value) {
    if (value && typeof value === 'object') {
      Object.values(value).forEach(freeze);
      Object.freeze(value);
    }
    return value;
  }

  function createCatalog(data) {
    if (!data || data.metadata?.schema !== 1 ||
        data.metadata.sourceUrl !== 'https://meshcoretel.ru/ru/OMS' || data.metadata.countrySelection !== 'RU' ||
        !Array.isArray(data.presets) || data.presets.length > 512 ||
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(data.metadata.snapshotAt) ||
        !Number.isFinite(Date.parse(data.metadata.snapshotAt))) throw new Error('Invalid preset snapshot');
    const copy = JSON.parse(JSON.stringify(data));
    const byId = new Map();
    for (const row of copy.presets) {
      if (!row || !/^[A-Z0-9]{3}$/.test(row.id) || row.id !== row.code ||
          byId.has(row.id) || typeof row.name !== 'string' || !row.name.trim() ||
          row.name.length > 100 || /[<>\x00-\x1f]/.test(row.name) ||
          typeof row.nameEn !== 'string' || row.nameEn.length > 100 ||
          /[<>\x00-\x1f]/.test(row.nameEn) || !validateRadio(row) ||
          row.frequencyMHz !== row.frequencyKHz / 1000 ||
          row.bandwidthKHz !== row.bandwidthHz / 1000 ||
          row.sourceUrl !== 'https://meshcoretel.ru/ru/' + row.code ||
          row.votes !== null || row.sourceUpdatedAt !== null) throw new Error('Invalid city preset');
      byId.set(row.id, freeze(row));
    }
    const collator = new Intl.Collator('ru', { sensitivity: 'base' });
    const rows = Array.from(byId.values()).sort((a, b) => collator.compare(a.name, b.name) || a.id.localeCompare(b.id));
    const normalize = text => String(text ?? '').trim().toLocaleLowerCase('ru').replace(/ё/g, 'е');
    return Object.freeze({
      metadata: freeze(copy.metadata),
      list(query = '') {
        const tokens = normalize(query).split(/\s+/).filter(Boolean);
        return rows.filter(row => {
          const text = normalize(row.name + ' ' + row.nameEn + ' ' + row.code);
          return tokens.every(token => text.includes(token));
        });
      },
      get(id) { return byId.get(String(id ?? '').trim().toUpperCase()) || null; },
      validateRadio,
    });
  }

  return Object.freeze({ ...createCatalog(snapshot), createCatalog });
});
