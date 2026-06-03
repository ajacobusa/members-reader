import tkinter as tk
from quoteforge.gui.app import QuoteForgeApp


def main() -> None:
    root = tk.Tk()
    QuoteForgeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
