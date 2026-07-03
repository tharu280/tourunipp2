import { getLodging, lodgingPriceLabel } from "../helpers";

const HOTEL_ICONS = ["🏨", "🏡", "🌿", "🏔️", "🌴", "🌺", "🏕️", "🏯"];

function hotelIcon(index) {
  return HOTEL_ICONS[index % HOTEL_ICONS.length];
}

export default function AccommodationSection({ plan }) {
  const stays = getLodging(plan);

  if (!stays.length) {
    return (
      <div className="empty-state">
        Accommodation details will appear once your plan is generated.
      </div>
    );
  }

  return (
    <div className="accom-scroll" id="section-accommodation" role="list" aria-label="Accommodation options">
      {stays.map((stay, i) => {
        const name = stay.display_name || stay.name || "Accommodation";
        const location = stay.location_name || stay.district || stay.address || "Sri Lanka";
        const price = lodgingPriceLabel(stay);
        const day = stay.day;
        
        // Mock rating between 4 and 5 stars for premium feel
        const rating = 4 + (i % 2 === 0 ? 1 : 0); 
        const stars = Array.from({ length: 5 }, (_, idx) => idx < rating);

        return (
          <div key={`stay-${i}`} className="accom-card" role="listitem">
            <div className="accom-thumb" aria-hidden="true">
              {hotelIcon(i)}
            </div>
            <div className="accom-body">
              <div className="accom-name" title={name}>{name}</div>
              <div className="accom-stars" aria-label={`${rating} stars`}>
                {stars.map((isFilled, idx) => (
                  <span key={idx} className="star-icon" style={{ opacity: isFilled ? 1 : 0.3 }}>
                    ★
                  </span>
                ))}
              </div>
              <div className="accom-location" title={location}>
                {location}
              </div>
              <div className="accom-price">
                {price} {day && <span className="accom-day-tag">Day {day}</span>}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
