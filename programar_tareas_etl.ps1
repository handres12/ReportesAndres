# Crear tareas programadas para ETLs: 6:00 y 8:00 (todos los dias)
# Ejecutar una vez como administrador o desde PowerShell con permisos normales.
# Las tareas se crean en el usuario actual.

$nombreBase = "BI_Andres_ETL"
$rutaProyecto = $PSScriptRoot
$bat = Join-Path $rutaProyecto "ejecutar_etls_6y8.bat"

if (-not (Test-Path $bat)) {
    Write-Host "No se encuentra ejecutar_etls_6y8.bat en: $rutaProyecto" -ForegroundColor Red
    exit 1
}

# Eliminar tareas anteriores si existen (para poder re-ejecutar el script)
$tarea6 = "${nombreBase}_6am"
$tarea8 = "${nombreBase}_8am"
Unregister-ScheduledTask -TaskName $tarea6 -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $tarea8 -Confirm:$false -ErrorAction SilentlyContinue

$accion = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $rutaProyecto
$desencadenador6 = New-ScheduledTaskTrigger -Daily -At "06:00"
$desencadenador8 = New-ScheduledTaskTrigger -Daily -At "08:00"
$config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $tarea6 -Action $accion -Trigger $desencadenador6 -Settings $config -Description "Actualiza datos BI Andres (Maestros, Ventas, Excel) a las 6:00"
Register-ScheduledTask -TaskName $tarea8 -Action $accion -Trigger $desencadenador8 -Settings $config -Description "Actualiza datos BI Andres (Maestros, Ventas, Excel) a las 8:00"

Write-Host "Tareas creadas:" -ForegroundColor Green
Write-Host "  - $tarea6  -> todos los dias a las 06:00"
Write-Host "  - $tarea8  -> todos los dias a las 08:00"
Write-Host ""
Write-Host "Para ver o editar: Panel de control -> Herramientas administrativas -> Programador de tareas" -ForegroundColor Cyan
