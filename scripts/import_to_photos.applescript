-- Optional helper: open sorted folders in Photos for manual import.
-- Photos.app has no stable CLI for bulk "add to iCloud"; use File > Import after review.

on run argv
	set importPath to item 1 of argv
	tell application "Photos"
		activate
	end tell
	tell application "Finder"
		open POSIX file importPath
	end tell
end run
