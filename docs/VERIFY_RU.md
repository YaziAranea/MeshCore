# Проверка SHA-256

SHA-256 позволяет убедиться, что скачанный UF2 совпадает с файлом, для которого создан релизный манифест. Контрольная сумма не доказывает безопасность исходного кода, но обнаруживает случайное повреждение и подмену относительно опубликованного `SHA256SUMS.txt`.

## Где находится эталон

Когда `v2.0.0-rc1` будет опубликован, скачайте из одного и того же GitHub Release:

- UF2 своей платы;
- `SHA256SUMS.txt`.

Не сравнивайте файл одного релиза с манифестом другого.

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

Скопируйте полученную 64-символьную строку и сравните её с соответствующей строкой `SHA256SUMS.txt`. Регистр букв не важен; каждый символ важен.

Автоматическая проверка всех файлов, находящихся рядом с манифестом:

```powershell
$failed = $false
Get-Content .\SHA256SUMS.txt | ForEach-Object {
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

Скрипт проверяет три публичных имени файлов, UF2 magic values, family ID, адрес старта `0x26000`, последовательность блоков и маркеры `SmartUI 2.0.0-rc1`. Он не доказывает работу на реальной плате.

Перед публикацией проверьте манифест в чистой временной папке ровно теми файлами, которые будут приложены к GitHub Release.
