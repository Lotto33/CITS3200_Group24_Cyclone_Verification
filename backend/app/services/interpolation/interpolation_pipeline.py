from app.services.interpolation.interpolate_best_track import (
    main as interpolate_best_track_main,
)
from app.services.interpolation.process_best_track import (
    main as process_best_track_main,
)
from app.services.relevant_system_extraction import (
    main as relevant_system_extraction_main,
)


def run_interpolation_pipeline() -> None:
    """Run the complete best-track interpolation pipeline."""

    print("\n=== 1. Extract relevant systems ===")
    relevant_system_extraction_main()

    print("\n=== 2. Process best-track data ===")
    process_best_track_main()

    print("\n=== 3. Interpolate best-track data ===")
    interpolate_best_track_main()

    print("\n=== Interpolation pipeline complete ===")


if __name__ == "__main__":
    run_interpolation_pipeline()