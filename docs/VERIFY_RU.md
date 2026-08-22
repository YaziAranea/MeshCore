# Проверка SHA-256

SHA-256 позволяет убедиться, что скачанный UF2 или BIN совпадает с опубликованным манифестом. Контрольная сумма не доказывает безопасность исходного кода, но обнаруживает случайное повреждение и подмену.

## Где находится эталон

Для стабильного `v2.0.0-rc1` скачивайте из одного [GitHub Release](https://github.com/YaziAranea/MeshCore/releases/tag/v2.0.0-rc1):

- UF2 своей платы;
- `SHA256SUMS.txt`.

Development-сборки `2.1.0-dev` находятся в [GitHub Actions](https://github.com/YaziAranea/MeshCore/actions/workflows/smartui-ci.yml):

- артефакт `smartui-ps17-validated-uf2` содержит три UF2 и `SHA256SUMS.txt`;
- артефакт `smartui-ps17-validated-esp32-bin` содержит V4.3/оба Wireless Paper профиля и `SHA256SUMS-ESP32.txt`.

GitHub хранит артефакт как ZIP. Распакуйте бинарники и их манифест в одну папку. Не сравнивайте файл одного Release/CI-run с манифестом другого.

## Windows PowerShell

Для одного файла:

```powershell
Get-FileHash -Algorithm SHA256 .\T096_FEM_SmartUI_v2.0.0-rc1.uf2
```

или:

```powershell
Get-FileHash -Algorithm SHA256 .\T114_SmartUI_v2.0.0-rc1.uf2
Get-FileHash -Algorithm SHA256 .\ProMicro_RA62_SmartUI_v2.0.0-rc1.uf2
```

Скопируйте полученную 64-символьную строку и сравните её с соответствующей строкой своего манифеста. Регистр букв не важен; каждый символ важен.

Автоматическая проверка всех файлов, находящихся рядом с манифестом:

```powershell
$failed = $false
$manifest = '.\SHA256SUMS.txt' # для ESP32 CI: '.\SHA256SUMS-ESP32.txt'
Get-Content $manifest | ForEach-Object {
  if ($_ -match '^([0-9a-fA-F]{64})\s{2}(.+)$') {
    $expected = $matches[1].ToLowerInvariant()
    $name = $matches[2]
    if (-not (Test-Path -LiteralPath $name)) {
      Write-Host "MISSING $name" -ForegroundColor Red
      $failed = $true
    } else {
      $actual = (Get-FileHash -LiteralPath $name -Algorithm SHA256).Hash.ToLowerInvariant()
      if ($actual -eq $expected) {
        Write-Host "OK      $name" -ForegroundColor Green
      } else {
        Write-Host "FAIL    $name" -ForegroundColor Red
        $failed = $true
      }
    }
  }
}
if ($failed) { throw 'SHA-256 verification failed' }
```

## Windows без PowerShell

```text
certutil -hashfile T096_FEM_SmartUI_v2.0.0-rc1.uf2 SHA256
```

## Linux

```bash
sha256sum -c SHA256SUMS.txt
# либо для ESP32 CI:
sha256sum -c SHA256SUMS-ESP32.txt
```

## macOS

Для одного файла:

```bash
shasum -a 256 T096_FEM_SmartUI_v2.0.0-rc1.uf2
```

## Если сумма не совпала

1. Не прошивайте файл.
2. Удалите его и скачайте заново из правильного GitHub Release.
3. Убедитесь, что браузер не переименовал или не распаковал файл.
4. Проверьте, что манифест относится к тому же тегу.
5. Если повторная загрузка снова даёт другую сумму, сообщите владельцу репозитория название файла, тег и фактический SHA-256. Не прикладывайте приватные ключи или дамп ноды.

## Для сопровождающего релиза

Контрольные суммы всегда генерируются заново после финальной сборки и переименования файлов. Нельзя копировать `SHA256SUMS.txt` от внутренней сборки или предыдущего тега, даже если исходники кажутся неизменными.

Перед публикацией запустите структурную проверку трёх UF2:

```text
python tools/validate_release_uf2.py firmware
```

Для V4.3 OLED и Wireless Paper отдельно проверьте ESP32-S3 пары:

```text
python tools/validate_release_esp32.py firmware
```

UF2-проверка контролирует magic values, family ID, адрес `0x26000`, блоки и version marker. ESP32-проверка контролирует image header `0xE9`, наличие application image по адресу `0x10000`, точное совпадение app-slice merged-файла с update-файлом и version marker. Ни одна из этих проверок не доказывает работу на реальной плате.

Перед публикацией проверьте манифест в чистой временной папке ровно теми файлами, которые будут приложены к GitHub Release.
