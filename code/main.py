import sys
from PySide6.QtWidgets import QApplication, QMessageBox, QMessageBox
from mascot import MascotWindow, validate_assets, validate_assets


def main():
    app = QApplication(sys.argv)

    missing = validate_assets()
    if missing:
        QMessageBox.critical(
            None,
            "DesktopMascot - Missing Assets",
            "Required files are missing from the assets folder:\n\n"
            + "\n".join(f"- {item}" for item in missing)
            + "\n\nPlease add the required files and restart DesktopMascot."
        )
        return 1

    mascot = MascotWindow()
    mascot.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())