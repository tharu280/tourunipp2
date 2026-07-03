import { getLodging, lodgingPriceLabel } from "../helpers";

const HOTEL_ICONS = ["🏨","🏡","🌿","🏔️","🌴","🌺","🏕️","🏯"];

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
        const location =
          stay.location_name || stay.district || stay.address || "Sri Lanka";
        const price = lodgingPriceLabel(stay);
        const day = stay.day;

        return (
          <div key={`stay-${i}`} className="accom-card" role="listitem">
            <div className="accom-img" aria-hidden="true">
              {hotelIcon(i)}
            </div>
            <div className="accom-name" title={name}>{name}</div>
            <div className="accom-location" title={location}>
              {location}
            </div>
            <div className="accom-price">
              {price}
              {day ? ` / night` : ""}
            </div>
          </div>
        );
      })}
    </div>
  );
}
