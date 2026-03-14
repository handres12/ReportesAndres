# Una sola tarea diaria DESPUES de las 8:00 (asumiendo que las tablas SQL estan al dia a las 8:00).
# Ejecutar una vez: .\programar_actualizacion_8am.ps1
# Crea: BI_Andres_Actualizacion_8am a las 08:15

$nombreTarea = "BI_Andres_Actualizacion_8am"
$rutaProyecto = $PSScriptRoot
$bat = Join-Path $rutaProyecto "actualizar_8am.bat"

if (-not (Test-Path $bat)) {
    Write-Host "No se encuentra actualizar_8am.bat en: $rutaProyecto" -ForegroundColor Red
    exit 1
}

Unregister-ScheduledTask -TaskName $nombreTarea -Confirm:$false -ErrorAction SilentlyContinue

$accion = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $rutaProyecto
$desencadenador = New-ScheduledTaskTrigger -Daily -At "08:15"
$config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $nombreTarea -Action $accion -Trigger $desencadenador -Settings $config `
    -Description "Pipeline BI Andres: ETLs + FTP 2025 + push GitHub. Ejecutar despues de las 8:00 (SQL al dia)."

Write-Host "Tarea creada: $nombreTarea -> todos los dias a las 08:15" -ForegroundColor Green
Write-Host "Asuncion: tablas SQL (Detalle, NEWACRVentas) estan al dia a las 08:00." -ForegroundColor Cyan
Write-Host "Para ver o editar: Panel de control -> Herramientas administrativas -> Programador de tareas" -ForegroundColor Cyan
