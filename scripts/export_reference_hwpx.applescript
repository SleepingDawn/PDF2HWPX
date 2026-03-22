on run argv
	if (count of argv) is less than 2 then error "usage: export_reference_hwpx.applescript <input.hwp> <output.hwpx>"
	set inputPath to item 1 of argv
	set outputPath to item 2 of argv
	
	tell application "Hancom Office HWP"
		activate
		open POSIX file inputPath
	end tell
	
	delay 3
	
	tell application "System Events"
		tell process "Hancom Office HWP"
			keystroke "S" using {command down, shift down}
			delay 2
			keystroke "g" using {command down, shift down}
			delay 1
			keystroke outputPath
			key code 36
			delay 1
			key code 36
			delay 2
		end tell
	end tell
	
	return outputPath
end run
