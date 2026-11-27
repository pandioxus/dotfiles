FILE="/sys/firmware/acpi/platform_profile"

inotifywait -m -e modify "$FILE" --format '%w%f' | while read FILE_CHANGED
do
    PROFILE=$(cat "$FILE_CHANGED")

    case "$PROFILE" in
        low-power)
            MSG="Power Saver Mode"
            ;;
        balanced)
            MSG="Balanced Mode"
            ;;
        performance)
            MSG="Performance Mode"
            ;;
        *)
            MSG="Unknown mode: $PROFILE"
            ;;
    esac

    notify-send "Lenovo Fn+Q" "$MSG"
done