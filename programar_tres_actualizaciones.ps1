# Tres actualizaciones diarias: 6:30, 8:00 y 10:00 (local + web).
# Ejecutar una vez: .\programar_tres_actualizaciones.ps1
# Cada ejecucion corre: ETLs + opcional FTP 2025 + push a GitHub (local y web actualizados).

$rutaProyecto = $PSScriptRoot
$bat = Join-Path $rutaProyecto "actualizar_8am.bat"

if (-not (Test-Path $bat)) {
    Write-Host "No se encuentra actualizar_8am.bat en: $rutaProyecto" -ForegroundColor Red
    exit 1
}

$tareas = @(
    @{ Nombre = "BI_Andres_Actualizacion_0630"; Hora = "06:30" },
    @{ Nombre = "BI_Andres_Actualizacion_8am";  Hora = "08:00" },
    @{ Nombre = "BI_Andres_Actualizacion_10am"; Hora = "10:00" }
)

$accion = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $rutaProyecto
$config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

foreach ($t in $tareas) {
    Unregister-ScheduledTask -TaskName $t.Nombre -Confirm:$false -ErrorAction SilentlyContinue
    $trigger = New-ScheduledTaskTrigger -Daily -At $t.Hora
    Register-ScheduledTask -TaskName $t.Nombre -Action $accion -Trigger $trigger -Settings $config `
        -Description "Pipeline BI Andres (ETLs + FTP + push GitHub). Actualizacion local y web."
    Write-Host "  $($t.Nombre) -> $($t.Hora)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Tareas creadas: 6:30, 8:00 y 10:00 (todos los dias)." -ForegroundColor Green
Write-Host "Cada una ejecuta: run_pipeline_diario.py (ETLs + opcional FTP + push a GitHub)." -ForegroundColor Cyan
Write-Host "Para ver o editar: Panel de control -> Herramientas administrativas -> Programador de tareas" -ForegroundColor Cyan
